"""Drives one end-to-end application: tailor CV, generate cover letter, open
the application page, fill the form, and either submit or escalate
(pipeline steps OPEN APPLICATION through SUBMIT). This is the one module
that needs a real, live browser and network access to actually run — it's
exercised by integration testing against a real ATS, not by this repo's
unit test suite (see tests/README notes).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jobagent.application.browser import BrowserSession
from jobagent.application.generic_filler import fill_form
from jobagent.config import DomainPolicy, Preferences, Profile
from jobagent.domain_policy import classify_url
from jobagent.generation.cover_letter import generate_cover_letter
from jobagent.generation.cv_tailor import tailor_resume
from jobagent.generation.llm import LLMClient
from jobagent.models import ApplicationResult, DomainPolicyStatus, JobListing, JobStatus, PendingInput, ScoreBreakdown
from jobagent.tracking.store import Store

logger = logging.getLogger(__name__)

_SUCCESS_PHRASES = [
    "application received",
    "application submitted",
    "thank you for applying",
    "thanks for applying",
    "we've received your application",
    "we have received your application",
    "successfully submitted",
]
_SUBMIT_LABEL_PATTERN = re.compile(r"submit|apply now|send application", re.IGNORECASE)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "job"


def _save_application_materials(output_dir: Path, job: JobListing, resume_text: str, cover_letter_text: str) -> tuple[Path, Path]:
    folder = output_dir / f"{_slugify(job.company)}-{_slugify(job.title)}-{datetime.utcnow():%Y%m%d%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    resume_path = folder / "resume.txt"
    cover_letter_path = folder / "cover_letter.txt"
    resume_path.write_text(resume_text, encoding="utf-8")
    cover_letter_path.write_text(cover_letter_text, encoding="utf-8")
    return resume_path, cover_letter_path


def _click_submit(session: BrowserSession) -> bool:
    button = session.page.get_by_role("button", name=_SUBMIT_LABEL_PATTERN).first
    if button.count() == 0:
        submit_input = session.page.locator('input[type="submit"]').first
        if submit_input.count() == 0:
            return False
        submit_input.click()
        return True
    button.click()
    return True


def _looks_successful(session: BrowserSession) -> bool:
    try:
        session.page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    body_text = session.page.locator("body").inner_text().lower()
    return any(phrase in body_text for phrase in _SUCCESS_PHRASES)


def apply_to_job(
    job: JobListing,
    score: ScoreBreakdown,
    profile: Profile,
    preferences: Preferences,
    domain_policy: DomainPolicy,
    store: Store,
    llm: LLMClient,
    output_dir: Path,
    headless: bool = True,
) -> ApplicationResult:
    domain_status = classify_url(job.application_url, domain_policy)
    if domain_status == DomainPolicyStatus.BLOCKED:
        return ApplicationResult(
            job=job, submitted=False, status=JobStatus.BLOCKED, score=score,
            notes=f"Application domain '{job.application_domain}' is blocked by policy.",
        )
    if domain_status == DomainPolicyStatus.MANUAL_REVIEW:
        pending = PendingInput(
            job_id=job.fingerprint,
            kind="manual_review_domain",
            question=f"'{job.application_domain}' is not a pre-approved application domain. Apply anyway?",
            context=job.application_url,
        )
        store.add_pending_input(pending)
        return ApplicationResult(
            job=job, submitted=False, status=JobStatus.MANUAL_REVIEW, score=score, pending_input=pending,
            notes="Application domain requires manual review before applying.",
        )

    try:
        resume_text = tailor_resume(profile.resume_text, job, profile, llm)
        cover_letter_text = generate_cover_letter(profile.resume_text, job, profile, llm)
    except Exception as exc:  # LLM unavailable/misconfigured, etc.
        logger.exception("CV/cover letter generation failed for %s", job.application_url)
        return ApplicationResult(job=job, submitted=False, status=JobStatus.FAILED, score=score, notes=str(exc))

    resume_path, cover_letter_path = _save_application_materials(output_dir, job, resume_text, cover_letter_text)

    try:
        with BrowserSession(headless=headless) as session:
            session.goto(job.application_url)

            if session.has_captcha():
                pending = PendingInput(
                    job_id=job.fingerprint, kind="captcha",
                    question="CAPTCHA/manual verification is required to proceed with this application.",
                    context=job.application_url,
                )
                store.add_pending_input(pending)
                return ApplicationResult(
                    job=job, submitted=False, status=JobStatus.MANUAL_REVIEW, score=score, pending_input=pending,
                    resume_path=str(resume_path), cover_letter_path=str(cover_letter_path),
                    notes="CAPTCHA encountered — needs manual verification.",
                )

            decisions = fill_form(
                session, profile, preferences, store, job=job, llm=llm,
                resume_path=str(resume_path), cover_letter_path=str(cover_letter_path),
            )
            escalations = [d for d in decisions if d.action == "escalate"]
            if escalations:
                pending = None
                for d in escalations:
                    p = PendingInput(
                        job_id=job.fingerprint,
                        kind=(d.source or "other"),
                        question=d.field.label or "(unlabeled required field)",
                        context=job.application_url,
                    )
                    store.add_pending_input(p)
                    pending = pending or p
                return ApplicationResult(
                    job=job, submitted=False, status=JobStatus.AWAITING_INPUT, score=score, pending_input=pending,
                    resume_path=str(resume_path), cover_letter_path=str(cover_letter_path),
                    notes=f"{len(escalations)} field(s) need input before this application can be submitted.",
                )

            if not _click_submit(session):
                return ApplicationResult(
                    job=job, submitted=False, status=JobStatus.MANUAL_REVIEW, score=score,
                    resume_path=str(resume_path), cover_letter_path=str(cover_letter_path),
                    notes="Could not locate a submit button — needs manual review.",
                )

            if _looks_successful(session):
                return ApplicationResult(
                    job=job, submitted=True, status=JobStatus.APPLIED, score=score,
                    resume_path=str(resume_path), cover_letter_path=str(cover_letter_path),
                    notes="Application submitted.",
                )
            return ApplicationResult(
                job=job, submitted=False, status=JobStatus.MANUAL_REVIEW, score=score,
                resume_path=str(resume_path), cover_letter_path=str(cover_letter_path),
                notes="Submitted the form but could not confirm success — needs manual review.",
            )
    except Exception as exc:
        logger.exception("Application automation failed for %s", job.application_url)
        return ApplicationResult(
            job=job, submitted=False, status=JobStatus.FAILED, score=score,
            resume_path=str(resume_path), cover_letter_path=str(cover_letter_path), notes=str(exc),
        )
