"""Shared data structures passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DomainPolicyStatus(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class MatchBand(str, Enum):
    EXCELLENT = "Excellent"
    STRONG = "Strong"
    POTENTIAL = "Potential"
    SKIP = "Skip"


class JobStatus(str, Enum):
    DISCOVERED = "discovered"
    SCORED = "scored"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    AWAITING_INPUT = "awaiting_input"
    MANUAL_REVIEW = "manual_review"
    APPLIED = "applied"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class SearchResult:
    """One raw hit from a search provider, before we know if it's a real job."""

    query: str
    title: str
    url: str
    snippet: str = ""


@dataclass
class JobListing:
    """A job posting, progressively enriched as it moves through the pipeline."""

    source_url: str
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    application_url: str = ""
    external_job_id: str = ""
    closing_date: Optional[datetime] = None
    remote_type: Optional[str] = None  # remote | hybrid | office
    employment_type: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    posted_date: Optional[datetime] = None
    discovered_via_query: str = ""
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    fingerprint: str = ""
    domain_policy: Optional[DomainPolicyStatus] = None
    status: JobStatus = JobStatus.DISCOVERED

    @property
    def application_domain(self) -> str:
        from urllib.parse import urlparse

        url = self.application_url or self.source_url
        return urlparse(url).netloc.lower().removeprefix("www.")


@dataclass
class ScoreBreakdown:
    skills_match: float = 0.0
    experience_match: float = 0.0
    role_match: float = 0.0
    location_match: float = 0.0
    industry_match: float = 0.0
    salary_match: float = 0.0
    preferences_match: float = 0.0
    total: float = 0.0
    band: MatchBand = MatchBand.SKIP

    def as_dict(self) -> dict:
        return {
            "skills_match": round(self.skills_match, 1),
            "experience_match": round(self.experience_match, 1),
            "role_match": round(self.role_match, 1),
            "location_match": round(self.location_match, 1),
            "industry_match": round(self.industry_match, 1),
            "salary_match": round(self.salary_match, 1),
            "preferences_match": round(self.preferences_match, 1),
            "total": round(self.total, 1),
            "band": self.band.value,
        }


@dataclass
class PendingInput:
    job_id: str
    question: str
    context: str = ""
    kind: str = "ambiguous_question"  # or: salary_expectation, work_authorization,
    # captcha, personal_preference
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ApplicationResult:
    job: JobListing
    submitted: bool
    status: JobStatus
    score: Optional[ScoreBreakdown] = None
    resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    notes: str = ""
    pending_input: Optional[PendingInput] = None


@dataclass
class RunSummary:
    started_at: datetime
    finished_at: Optional[datetime] = None
    jobs_discovered: int = 0
    jobs_relevant: int = 0
    jobs_skipped: int = 0
    applications_submitted: int = 0
    waiting_for_input: int = 0
    manual_verification_required: int = 0
    failed: int = 0
    top_applications: list = field(default_factory=list)  # list[ApplicationResult]
