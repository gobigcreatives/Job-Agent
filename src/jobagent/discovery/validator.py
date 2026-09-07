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

# Job boards' search-results pages ("816 Digital Marketing Executive jobs
# in United Kingdom", "1,548 Social Media Manager jobs in London") get
# titled almost identically to how a single vacancy would be, so they can
# slip past every other check and get scored as if they were one real job
# — with no actual vacancy to apply to at that URL. These patterns are
# specific enough to real aggregator SEO titles that they shouldn't false-
# positive on a genuine single job title.
_LISTING_PAGE_PATTERNS = [
    re.compile(r"^\s*[\d,]+\+?\s+.{0,80}?\bjobs?\b", re.IGNORECASE),
    re.compile(r"\bjobs?\s+in\s+.{0,60}$", re.IGNORECASE),
    re.compile(r"\bsearch\s+results\b", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*\s+(?:vacanc(?:y|ies)|results|jobs?)\s+found\b", re.IGNORECASE),
]


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


def _looks_like_listing_page(job: JobListing) -> bool:
    title = job.title.strip()
    return any(pattern.search(title) for pattern in _LISTING_PAGE_PATTERNS)


def is_still_open(job: JobListing, http_status: int | None = None) -> bool:
    """True only if the listing looks like a real, currently-open vacancy.
    `http_status` is the response code for the (final, redirect-followed)
    listing page, if available."""
    if http_status is not None and http_status >= 400:
        return False
    if not _looks_like_real_vacancy(job):
        return False
    if _looks_like_listing_page(job):
        return False
    if _is_expired_by_date(job):
        return False
    if _mentions_expired(job):
        return False
    return True
