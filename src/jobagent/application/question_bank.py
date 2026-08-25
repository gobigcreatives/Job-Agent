"""Answers standard application questions from configuration, without
involving the user, and escalates only what genuinely requires them
(requirement #4). Every question is classified into a coarse `kind`
(work_authorization, salary_expectation, ...); once the user answers a
`kind` for the first time (via `jobagent answer`), that answer is cached in
the Store and reused automatically for every later application — the same
category of question is never asked twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from jobagent.config import Preferences, Profile
from jobagent.models import JobListing
from jobagent.tracking.store import Store

_KIND_KEYWORDS: dict[str, list[str]] = {
    "work_authorization": [
        "right to work",
        "authorised to work",
        "authorized to work",
        "work authorisation",
        "work authorization",
        "eligible to work",
        "legally able to work",
        "legally eligible",
    ],
    "sponsorship": ["require sponsorship", "need sponsorship", "visa sponsorship", "sponsor your"],
    "notice_period": ["notice period"],
    "relocation": ["willing to relocate", "relocation"],
    "salary_expectation": [
        "salary expectation",
        "expected salary",
        "desired salary",
        "salary requirement",
        "compensation expectation",
        "day rate",
    ],
    "linkedin_url": ["linkedin"],
    "portfolio_url": ["portfolio", "personal website", "personal site"],
    "referral_source": ["how did you hear", "referral source", "how did you find"],
    "full_name": ["full name", "your name", "first and last name"],
    "email": ["email address"],
    "phone": ["phone number", "contact number", "telephone"],
    "diversity_optional": [
        "gender",
        "ethnicity",
        "disab",
        "veteran",
        "equal opportunities",
        "sexual orientation",
        "ethnic background",
    ],
    "cover_letter_prompt": [
        "why do you want",
        "why are you interested",
        "tell us about yourself",
        "why should we hire",
        "what makes you",
        "why this role",
    ],
}


@dataclass
class QuestionAnswer:
    answer: str
    confidence: float
    source: str


def classify_question(question: str) -> str:
    q = question.lower()
    for kind, keywords in _KIND_KEYWORDS.items():
        if any(k in q for k in keywords):
            return kind
    return "other"


def _resolve_from_config(kind: str, profile: Profile, preferences: Preferences) -> Optional[str]:
    if kind == "work_authorization":
        return profile.work_authorization
    if kind == "sponsorship":
        requires = profile.default_answers.get("requires_sponsorship", False)
        return "Yes" if requires else "No"
    if kind == "notice_period":
        return profile.default_answers.get("notice_period")
    if kind == "relocation":
        willing = profile.default_answers.get("willing_to_relocate", False)
        return "Yes" if willing else "No"
    if kind == "salary_expectation" and preferences.salary_minimum:
        return (
            f"{preferences.salary_currency} {preferences.salary_minimum:,.0f}+ "
            f"({preferences.salary_currency} {preferences.salary_minimum:,.0f} minimum, "
            "open to discussion for the right role)"
        )
    if kind == "linkedin_url":
        return profile.linkedin_url or None
    if kind == "portfolio_url":
        return profile.portfolio_url or None
    if kind == "referral_source":
        return profile.default_answers.get("referral_source")
    if kind == "full_name":
        return profile.name
    if kind == "email":
        return profile.email
    if kind == "phone":
        return profile.phone
    return None


def answer_question(
    question: str,
    profile: Profile,
    preferences: Preferences,
    store: Store,
    job: Optional[JobListing] = None,
    llm=None,
) -> Optional[QuestionAnswer]:
    kind = classify_question(question)

    learned = store.get_learned_answer(kind)
    if learned:
        return QuestionAnswer(answer=learned, confidence=0.9, source=f"learned:{kind}")

    from_config = _resolve_from_config(kind, profile, preferences)
    if from_config:
        return QuestionAnswer(answer=from_config, confidence=0.95, source=f"config:{kind}")

    if kind == "diversity_optional":
        # Standard practice: these are optional monitoring questions. Answer
        # them rather than stall an otherwise-complete application on them.
        return QuestionAnswer(answer="Prefer not to say", confidence=0.8, source="policy:optional_diversity")

    if kind == "cover_letter_prompt" and llm is not None and job is not None:
        from jobagent.generation.cover_letter import generate_cover_letter

        try:
            text = generate_cover_letter(profile.resume_text, job, profile, llm)
            return QuestionAnswer(answer=text, confidence=0.7, source="llm:cover_letter_prompt")
        except Exception:
            return None

    return None
