"""Wires every stage together in the order from the spec:

USER PROFILE -> JOB SEARCH PREFERENCES -> GENERATE SEARCH QUERIES ->
SEARCH GOOGLE -> COLLECT JOB RESULTS -> DEDUPLICATE -> EXTRACT JOB DETAILS ->
IDENTIFY ORIGINAL APPLICATION URL -> CHECK DOMAIN POLICY ->
ANALYSE JOB DESCRIPTION -> CALCULATE MATCH SCORE -> FILTER OUT POOR MATCHES ->
TAILOR CV -> GENERATE COVER LETTER -> OPEN APPLICATION -> FILL APPLICATION ->
HANDLE QUESTIONS -> SUBMIT -> SEND EMAIL IF APPROPRIATE -> TRACK APPLICATION

Deduplication runs twice: once on the raw search snippets (cheap, avoids
fetching the same listing twice within one run) and again after full
extraction (catches duplicates that only become obvious once we have the
real title/company/description, e.g. two boards mirroring the same
Greenhouse posting under different link text).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from jobagent.config import AppConfig
from jobagent.dedup import compute_fingerprint, deduplicate
from jobagent.discovery import extract_job_details, fetch_page, is_still_open, resolve_application_url
from jobagent.domain_policy import classify_url
from jobagent.generation.llm import LLMClient
from jobagent.learning import prioritize_queries
from jobagent.models import (
    ApplicationResult,
    DomainPolicyStatus,
    JobListing,
    JobStatus,
    MatchBand,
    RunSummary,
    SearchResult,
)
from jobagent.scoring import score_job
from jobagent.search.query_builder import generate_queries
from jobagent.tracking.store import Store

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {
    JobStatus.APPLIED, JobStatus.BLOCKED, JobStatus.SKIPPED, JobStatus.EXPIRED, JobStatus.FAILED,
}


def _search_results_to_jobs(results: list[SearchResult]) -> list[JobListing]:
    jobs = []
    for r in results:
        job = JobListing(source_url=r.url, title=r.title, description=r.snippet, discovered_via_query=r.query)
        job.fingerprint = compute_fingerprint(job)
        jobs.append(job)
    return jobs


def run_cycle(
    config: AppConfig,
    search_provider,
    store: Store,
    llm: Optional[LLMClient] = None,
    apply_enabled: bool = True,
    headless: bool = True,
    session: Optional[requests.Session] = None,
) -> RunSummary:
    profile, preferences, domain_policy = config.profile, config.preferences, config.domain_policy
    session = session or requests.Session()
    output_dir = config.data_dir / "applications"

    started_at = datetime.utcnow()
    run_id = store.start_run(started_at)
    summary = RunSummary(started_at=started_at)

    all_queries = generate_queries(profile, preferences)
    queries = prioritize_queries(all_queries, store, preferences.search.max_queries_per_run)
    logger.info("Running %d of %d generated queries", len(queries), len(all_queries))

    raw_results: list[SearchResult] = []
    per_query_found: dict[str, int] = {}
    for query in queries:
        try:
            results = search_provider.search(query, preferences.search.max_results_per_query)
        except Exception:
            logger.exception("Search failed for query: %s", query)
            results = []
        per_query_found[query] = len(results)
        raw_results.extend(results)

    summary.jobs_discovered = len(raw_results)

    candidate_jobs = deduplicate(_search_results_to_jobs(raw_results))

    extracted_jobs: list[JobListing] = []
    for job in candidate_jobs:
        existing_status = store.get_status_by_source_url(job.source_url)
        if existing_status in {s.value for s in _TERMINAL_STATUSES}:
            continue  # already handled in a previous run

        try:
            response = fetch_page(job.source_url, session=session)
        except requests.RequestException as exc:
            logger.warning("Could not fetch %s: %s", job.source_url, exc)
            continue

        if not response.ok:
            continue

        details = extract_job_details(response.url, response.text)
        details.source_url = job.source_url
        details.discovered_via_query = job.discovered_via_query
        details.discovered_at = job.discovered_at

        if not is_still_open(details, response.status_code):
            details.fingerprint = compute_fingerprint(details)
            details.status = JobStatus.EXPIRED
            store.upsert_job(details)
            continue

        application_domain_status = classify_url(response.url, domain_policy)
        if application_domain_status == DomainPolicyStatus.ALLOWED:
            details.application_url = response.url
        else:
            details.application_url = resolve_application_url(response.url, response.text, domain_policy)
        details.domain_policy = classify_url(details.application_url, domain_policy)
        details.fingerprint = compute_fingerprint(details)
        extracted_jobs.append(details)

    extracted_jobs = deduplicate(extracted_jobs)

    per_query_matched: dict[str, int] = {}
    per_query_applied: dict[str, int] = {}
    top_applications: list[ApplicationResult] = []
    applications_this_run = 0
    limit_reached = False

    for job in extracted_jobs:
        score = score_job(job, profile, preferences)

        if score.band == MatchBand.SKIP or score.total < preferences.limits.min_match_score:
            job.status = JobStatus.SKIPPED
            store.upsert_job(job, score)
            summary.jobs_skipped += 1
            continue

        summary.jobs_relevant += 1
        per_query_matched[job.discovered_via_query] = per_query_matched.get(job.discovered_via_query, 0) + 1

        if job.domain_policy == DomainPolicyStatus.BLOCKED:
            job.status = JobStatus.BLOCKED
            store.upsert_job(job, score)
            summary.jobs_skipped += 1
            continue

        eligible_to_apply = (
            apply_enabled
            and score.total >= preferences.scoring.auto_apply_min_score
            and job.domain_policy == DomainPolicyStatus.ALLOWED
        )

        if not eligible_to_apply:
            job.status = JobStatus.SCORED
            store.upsert_job(job, score)
            top_applications.append(ApplicationResult(job=job, submitted=False, status=JobStatus.SCORED, score=score))
            continue

        if not limit_reached:
            company_count = store.count_applications_for_company(job.company)
            if (
                store.count_applications_today() + applications_this_run >= preferences.limits.max_applications_per_day
            ):
                limit_reached = True
                logger.info("Daily application limit reached — remaining matches will not be applied to this run.")
            elif store.count_applications_this_hour() + applications_this_run >= preferences.limits.max_applications_per_hour:
                limit_reached = True
                logger.info("Hourly application limit reached — remaining matches will not be applied to this run.")
            elif company_count >= preferences.limits.max_applications_per_company:
                job.status = JobStatus.SCORED
                store.upsert_job(job, score)
                top_applications.append(ApplicationResult(job=job, submitted=False, status=JobStatus.SCORED, score=score))
                continue

        if limit_reached:
            job.status = JobStatus.SCORED
            store.upsert_job(job, score)
            top_applications.append(ApplicationResult(job=job, submitted=False, status=JobStatus.SCORED, score=score))
            continue

        from jobagent.application.runner import apply_to_job

        result = apply_to_job(
            job, score, profile, preferences, domain_policy, store, llm, output_dir, headless=headless
        )
        store.upsert_job(job, score)
        store.record_application(result)
        top_applications.append(result)

        if result.status == JobStatus.APPLIED:
            applications_this_run += 1
            summary.applications_submitted += 1
            per_query_applied[job.discovered_via_query] = per_query_applied.get(job.discovered_via_query, 0) + 1
        elif result.status == JobStatus.AWAITING_INPUT:
            summary.waiting_for_input += 1
        elif result.status == JobStatus.MANUAL_REVIEW:
            summary.manual_verification_required += 1
        elif result.status in (JobStatus.FAILED, JobStatus.BLOCKED):
            summary.failed += 1

    for query in queries:
        store.record_query_run(
            query,
            jobs_found=per_query_found.get(query, 0),
            jobs_matched=per_query_matched.get(query, 0),
            applications_submitted=per_query_applied.get(query, 0),
            successful_applications=per_query_applied.get(query, 0),
        )

    summary.finished_at = datetime.utcnow()
    summary.top_applications = top_applications
    store.finish_run(run_id, summary)
    return summary
