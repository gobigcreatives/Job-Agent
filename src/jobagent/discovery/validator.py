"""Verifies a listing is an actual, currently-open vacancy before it's
scored or applied to (requirement #9). We deliberately err toward skipping
when unsure — a missed job is recoverable next run, a wasted application to
an expired posting is not.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from jobagent.models import JobListing

_EXPIRED_PHRASES = [
    "no longer accepting applications",
    "position has been filled",
    "this position has been filled",
    "job has expired",
    "vacancy is closed",
    "vacancy has closed",
    "this vacancy is now closed",
    "posting has expired",
    "no longer available",
    "job posting is no longer active",
    "we are no longer accepting",
]

_MIN_TITLE_LEN = 3
_MIN_DESCRIPTION_LEN = 80


def _is_expired_by_date(job: JobListing) -> bool:
    if job.closing_date is None:
        return False
    closing = job.closing_date
    now = datetime.now(closing.tzinfo) if closing.tzinfo else datetime.utcnow()
    return closing < now


def _mentions_expired(job: JobListing) -> bool:
    text = job.description.lower()
    return any(phrase in text for phrase in _EXPIRED_PHRASES)


def _looks_like_real_vacancy(job: JobListing) -> bool:
    return len(job.title.strip()) >= _MIN_TITLE_LEN and len(job.description.strip()) >= _MIN_DESCRIPTION_LEN


def is_still_open(job: JobListing, http_status: int | None = None) -> bool:
    """True only if the listing looks like a real, currently-open vacancy.
    `http_status` is the response code for the (final, redirect-followed)
    listing page, if available."""
    if http_status is not None and http_status >= 400:
        return False
    if not _looks_like_real_vacancy(job):
        return False
    if _is_expired_by_date(job):
        return False
    if _mentions_expired(job):
        return False
    return True
