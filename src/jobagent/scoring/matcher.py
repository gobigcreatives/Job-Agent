"""Weighted match scoring (requirement #8). Every factor returns a 0-100
sub-score; the weighted sum is the total. Weights and band cutoffs come from
preferences.yaml — nothing here is a magic number the user can't reach.

Excluded companies and excluded roles are a hard veto: they force the job to
Skip regardless of how well everything else matches, because the user has
explicitly said "never these".
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from jobagent.config import Preferences, Profile
from jobagent.models import JobListing, MatchBand, ScoreBreakdown

_EXPERIENCE_PATTERN = re.compile(
    r"(?P<min>\d+)\s*(?:\+|-\s*(?P<max>\d+))?\s*years?\b", re.IGNORECASE
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _skills_match(job: JobListing, profile: Profile) -> float:
    if not profile.skills:
        return 50.0
    haystack = _normalize(f"{job.title} {job.description}")
    hits = sum(1 for skill in profile.skills if _normalize(skill) in haystack)
    return _clamp(100.0 * hits / len(profile.skills))


def _extract_required_years(description: str) -> float | None:
    match = _EXPERIENCE_PATTERN.search(description or "")
    if not match:
        return None
    lo = float(match.group("min"))
    hi = match.group("max")
    return (lo + float(hi)) / 2 if hi else lo


def _experience_match(job: JobListing, profile: Profile, prefs: Preferences) -> float:
    required = _extract_required_years(job.description)
    if required is None:
        # No explicit requirement stated — neither penalise nor reward.
        return 60.0
    if prefs.experience_min_years <= profile.experience_years <= prefs.experience_max_years:
        base = 100.0
    else:
        base = 70.0
    gap = abs(required - profile.experience_years)
    return _clamp(base - gap * 12.0)


def _role_match(job: JobListing, prefs: Preferences) -> tuple[float, bool]:
    title = _normalize(job.title)
    if not title:
        return 50.0, False
    best = max((SequenceMatcher(None, title, _normalize(r)).ratio() for r in prefs.target_roles), default=0.0)
    excluded = any(SequenceMatcher(None, title, excl).ratio() >= 0.8 or excl in title for excl in prefs.excluded_roles)
    return _clamp(best * 100.0), excluded


def _location_match(job: JobListing, prefs: Preferences) -> float:
    remote_type = (job.remote_type or "").lower()
    if remote_type and remote_type in [r.lower() for r in prefs.remote_accepted]:
        return 100.0
    location = _normalize(job.location)
    if location and any(_normalize(loc) in location or location in _normalize(loc) for loc in prefs.locations):
        return 90.0
    if not location and not remote_type:
        return 40.0
    return 20.0


def _industry_match(job: JobListing, prefs: Preferences) -> float:
    if not prefs.industries:
        return 50.0
    haystack = _normalize(f"{job.company} {job.description}")
    hits = sum(1 for industry in prefs.industries if _normalize(industry) in haystack)
    if hits:
        return _clamp(60.0 + 40.0 * hits / len(prefs.industries))
    return 40.0


def _salary_match(job: JobListing, prefs: Preferences) -> float:
    if prefs.salary_minimum <= 0:
        return 100.0
    candidate = job.salary_max or job.salary_min
    if candidate is None:
        return 55.0  # unknown — neutral, don't penalise listings that omit salary
    if candidate >= prefs.salary_minimum:
        return 100.0
    shortfall_ratio = (prefs.salary_minimum - candidate) / prefs.salary_minimum
    return _clamp(100.0 - shortfall_ratio * 150.0)


def _preferences_match(job: JobListing, prefs: Preferences) -> tuple[float, bool]:
    excluded = bool(job.company) and _normalize(job.company) in prefs.excluded_companies
    employment_type = (job.employment_type or "").lower()
    if not employment_type:
        return 60.0, excluded
    normalized_types = [t.lower() for t in prefs.employment_types]
    return (100.0 if employment_type in normalized_types else 30.0), excluded


def _band(total: float, prefs: Preferences) -> MatchBand:
    bands = prefs.scoring.bands
    if total >= bands["excellent"]:
        return MatchBand.EXCELLENT
    if total >= bands["strong"]:
        return MatchBand.STRONG
    if total >= bands["potential"]:
        return MatchBand.POTENTIAL
    return MatchBand.SKIP


def score_job(job: JobListing, profile: Profile, preferences: Preferences) -> ScoreBreakdown:
    role_score, role_excluded = _role_match(job, preferences)
    prefs_score, company_excluded = _preferences_match(job, preferences)

    breakdown = ScoreBreakdown(
        skills_match=_skills_match(job, profile),
        experience_match=_experience_match(job, profile, preferences),
        role_match=role_score,
        location_match=_location_match(job, preferences),
        industry_match=_industry_match(job, preferences),
        salary_match=_salary_match(job, preferences),
        preferences_match=prefs_score,
    )

    if role_excluded or company_excluded:
        breakdown.total = 0.0
        breakdown.band = MatchBand.SKIP
        return breakdown

    weights = preferences.scoring.weights
    total = sum(getattr(breakdown, factor) * weight for factor, weight in weights.items())
    breakdown.total = round(_clamp(total), 1)
    breakdown.band = _band(breakdown.total, preferences)
    return breakdown
