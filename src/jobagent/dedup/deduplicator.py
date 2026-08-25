"""The same vacancy routinely shows up multiple times: on Google, mirrored by
several job boards, and on the company's own site. This module recognises
those as one underlying job so we only ever create one application record
for it (requirement #7).

Two listings are treated as duplicates if ANY of these hold:
  1. Same external job id (when both are known), e.g. a Greenhouse job id.
  2. Same canonical URL (application_url if set, else source_url), after
     stripping tracking query params and trailing slashes.
  3. Same normalized company + location, and a fuzzy title match.
  4. Near-identical job descriptions (catches "same job, different title
     capitalisation/wording, mirrored on a different board").
Matches are transitive (union-find), so a chain of near-duplicates collapses
into a single group even if the first and last don't directly match.
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from jobagent.models import JobListing

_TITLE_SIMILARITY_THRESHOLD = 0.85
_DESCRIPTION_SIMILARITY_THRESHOLD = 0.90
_MIN_DESCRIPTION_LEN_FOR_COMPARISON = 200
_TRACKING_PARAM_PREFIXES = ("utm_", "gh_", "gh_src", "trk", "ref", "src", "fbclid", "gclid")


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower().removeprefix("www."), path, "", urlencode(kept), ""))


def compute_fingerprint(job: JobListing) -> str:
    """A stable, human-inspectable key for a listing. Not used directly for
    matching (see `deduplicate`) but stored on the record for debugging and
    as the DB dedup key for exact repeats."""
    url = canonical_url(job.application_url or job.source_url)
    key = "|".join(
        [
            _normalize_text(job.company),
            _normalize_text(job.title),
            _normalize_text(job.location),
            job.external_job_id.strip().lower(),
            url,
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _title_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, _normalize_text(a), _normalize_text(b)).ratio() >= _TITLE_SIMILARITY_THRESHOLD


def _description_similar(a: str, b: str) -> bool:
    if len(a) < _MIN_DESCRIPTION_LEN_FOR_COMPARISON or len(b) < _MIN_DESCRIPTION_LEN_FOR_COMPARISON:
        return False
    return SequenceMatcher(None, a, b).ratio() >= _DESCRIPTION_SIMILARITY_THRESHOLD


def _is_duplicate(a: JobListing, b: JobListing) -> bool:
    if a.external_job_id and b.external_job_id and a.external_job_id.strip().lower() == b.external_job_id.strip().lower():
        return True
    url_a = canonical_url(a.application_url or a.source_url)
    url_b = canonical_url(b.application_url or b.source_url)
    if url_a and url_a == url_b:
        return True
    same_company = _normalize_text(a.company) == _normalize_text(b.company) and a.company
    same_location = _normalize_text(a.location) == _normalize_text(b.location)
    if same_company and same_location and _title_similar(a.title, b.title):
        return True
    if _description_similar(a.description, b.description):
        return True
    return False


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _merge_group(jobs: list[JobListing]) -> JobListing:
    """Keep the richest record: longest description, and prefer an
    application_url that's already been resolved over a bare source_url."""
    best = max(jobs, key=lambda j: (bool(j.application_url), len(j.description or "")))
    best.fingerprint = compute_fingerprint(best)
    return best


def deduplicate(jobs: list[JobListing]) -> list[JobListing]:
    n = len(jobs)
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if _is_duplicate(jobs[i], jobs[j]):
                uf.union(i, j)

    groups: dict[int, list[JobListing]] = {}
    for i, job in enumerate(jobs):
        groups.setdefault(uf.find(i), []).append(job)

    return [_merge_group(group) for group in groups.values()]
