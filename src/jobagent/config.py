"""Loads and validates the three config files: profile, preferences, domain
policy. All three are plain YAML so they're editable without touching code
(requirement: "editable without changing the application code")."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_DIR = Path(os.environ.get("JOBAGENT_CONFIG_DIR", "config"))

_VALID_FREQUENCIES = {"manual", "hourly", "every_6_hours", "daily_morning"}
_SCORING_FACTORS = (
    "skills_match",
    "experience_match",
    "role_match",
    "location_match",
    "industry_match",
    "salary_match",
    "preferences_match",
)


class ConfigError(ValueError):
    """Raised for missing/invalid configuration — fails loudly rather than
    silently running with nonsensical settings."""


@dataclass
class Profile:
    name: str
    email: str
    phone: str
    location: str
    work_authorization: str
    resume_text_path: str
    skills: list[str] = field(default_factory=list)
    experience_years: float = 0
    seniority: str = ""
    industries: list[str] = field(default_factory=list)
    linkedin_url: str = ""
    portfolio_url: str = ""
    default_answers: dict[str, Any] = field(default_factory=dict)

    @property
    def resume_text(self) -> str:
        path = Path(self.resume_text_path)
        if not path.exists():
            raise ConfigError(
                f"profile.resume_text_path points to {path}, which does not exist. "
                "Copy config/resume.example.md to that path and fill it in."
            )
        return path.read_text(encoding="utf-8")


@dataclass
class ScoringConfig:
    weights: dict[str, float]
    bands: dict[str, float]
    auto_apply_min_score: float


@dataclass
class LimitsConfig:
    max_applications_per_day: int
    max_applications_per_hour: int
    max_applications_per_company: int
    min_match_score: float


@dataclass
class SearchConfig:
    max_queries_per_run: int
    max_results_per_query: int
    cache_ttl_hours: float
    request_delay_seconds: float


@dataclass
class ScheduleConfig:
    frequency: str
    run_time: str
    timezone: str


@dataclass
class Preferences:
    target_roles: list[str]
    locations: list[str]
    remote_accepted: list[str]
    employment_types: list[str]
    salary_minimum: float
    salary_currency: str
    experience_min_years: float
    experience_max_years: float
    industries: list[str]
    excluded_companies: list[str]
    excluded_roles: list[str]
    scoring: ScoringConfig
    limits: LimitsConfig
    search: SearchConfig
    schedule: ScheduleConfig


@dataclass
class DomainPolicy:
    blocked: set[str]
    allowed: set[str]
    manual_review: set[str]
    default_policy: str


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        example = path.with_suffix("").with_name(path.stem + ".example" + path.suffix)
        hint = f" (an example is available at {example})" if example.exists() else ""
        raise ConfigError(f"Missing config file: {path}{hint}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")
    return data


def load_profile(config_dir: Path | str = DEFAULT_CONFIG_DIR) -> Profile:
    data = _load_yaml(Path(config_dir) / "profile.yaml")
    candidate = data.get("candidate", {})
    required = ["name", "email", "phone", "location", "work_authorization", "resume_text_path"]
    missing = [f for f in required if not candidate.get(f)]
    if missing:
        raise ConfigError(f"profile.yaml candidate section missing: {', '.join(missing)}")
    resume_text_path = Path(candidate["resume_text_path"])
    if not resume_text_path.is_absolute():
        resume_text_path = Path(config_dir) / resume_text_path

    return Profile(
        name=candidate["name"],
        email=candidate["email"],
        phone=candidate["phone"],
        location=candidate["location"],
        work_authorization=candidate["work_authorization"],
        resume_text_path=str(resume_text_path),
        linkedin_url=candidate.get("linkedin_url", ""),
        portfolio_url=candidate.get("portfolio_url", ""),
        skills=list(data.get("skills", [])),
        experience_years=float(data.get("experience_years", 0)),
        seniority=data.get("seniority", ""),
        industries=list(data.get("industries", [])),
        default_answers=dict(data.get("default_answers", {})),
    )


def _validate_scoring(raw: dict) -> ScoringConfig:
    weights = {k: float(v) for k, v in raw.get("weights", {}).items()}
    missing = set(_SCORING_FACTORS) - set(weights)
    if missing:
        raise ConfigError(f"preferences.yaml scoring.weights missing factors: {', '.join(sorted(missing))}")
    extra = set(weights) - set(_SCORING_FACTORS)
    if extra:
        raise ConfigError(f"preferences.yaml scoring.weights has unknown factors: {', '.join(sorted(extra))}")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ConfigError(f"preferences.yaml scoring.weights must sum to 1.0 (got {total:.3f})")

    bands = {k: float(v) for k, v in raw.get("bands", {}).items()}
    for key in ("excellent", "strong", "potential"):
        if key not in bands:
            raise ConfigError(f"preferences.yaml scoring.bands missing '{key}'")
    if not (bands["excellent"] > bands["strong"] > bands["potential"]):
        raise ConfigError("preferences.yaml scoring.bands must satisfy excellent > strong > potential")

    auto_apply_min = float(raw.get("auto_apply_min_score", bands["strong"]))
    return ScoringConfig(weights=weights, bands=bands, auto_apply_min_score=auto_apply_min)


def load_preferences(config_dir: Path | str = DEFAULT_CONFIG_DIR) -> Preferences:
    data = _load_yaml(Path(config_dir) / "preferences.yaml")

    target_roles = list(data.get("target_roles", []))
    if not target_roles:
        raise ConfigError("preferences.yaml target_roles must list at least one role")
    locations = list(data.get("locations", []))
    if not locations:
        raise ConfigError("preferences.yaml locations must list at least one location")

    salary = data.get("salary", {})
    experience = data.get("experience", {})
    remote = data.get("remote", {})
    limits = data.get("limits", {})
    search = data.get("search", {})
    schedule = data.get("schedule", {})

    frequency = schedule.get("frequency", "manual")
    if frequency not in _VALID_FREQUENCIES:
        raise ConfigError(
            f"preferences.yaml schedule.frequency '{frequency}' must be one of {sorted(_VALID_FREQUENCIES)}"
        )

    return Preferences(
        target_roles=target_roles,
        locations=locations,
        remote_accepted=list(remote.get("accepted", ["remote", "hybrid", "office"])),
        employment_types=list(data.get("employment_types", ["full_time"])),
        salary_minimum=float(salary.get("minimum", 0)),
        salary_currency=salary.get("currency", "GBP"),
        experience_min_years=float(experience.get("min_years", 0)),
        experience_max_years=float(experience.get("max_years", 99)),
        industries=list(data.get("industries", [])),
        excluded_companies=[c.lower() for c in data.get("excluded_companies", [])],
        excluded_roles=[r.lower() for r in data.get("excluded_roles", [])],
        scoring=_validate_scoring(data.get("scoring", {})),
        limits=LimitsConfig(
            max_applications_per_day=int(limits.get("max_applications_per_day", 10)),
            max_applications_per_hour=int(limits.get("max_applications_per_hour", 5)),
            max_applications_per_company=int(limits.get("max_applications_per_company", 2)),
            min_match_score=float(limits.get("min_match_score", 70)),
        ),
        search=SearchConfig(
            max_queries_per_run=int(search.get("max_queries_per_run", 20)),
            max_results_per_query=int(search.get("max_results_per_query", 10)),
            cache_ttl_hours=float(search.get("cache_ttl_hours", 12)),
            request_delay_seconds=float(search.get("request_delay_seconds", 2)),
        ),
        schedule=ScheduleConfig(
            frequency=frequency,
            run_time=schedule.get("run_time", "08:00"),
            timezone=schedule.get("timezone", "UTC"),
        ),
    )


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("www.")


def load_domain_policy(config_dir: Path | str = DEFAULT_CONFIG_DIR) -> DomainPolicy:
    data = _load_yaml(Path(config_dir) / "domain_policy.yaml")
    default_policy = data.get("default_policy", "manual_review")
    if default_policy not in ("allowed", "blocked", "manual_review"):
        raise ConfigError("domain_policy.yaml default_policy must be one of allowed/blocked/manual_review")
    policy = DomainPolicy(
        blocked={_normalize_domain(d) for d in data.get("blocked", [])},
        allowed={_normalize_domain(d) for d in data.get("allowed", [])},
        manual_review={_normalize_domain(d) for d in data.get("manual_review", [])},
        default_policy=default_policy,
    )
    for required in ("linkedin.com", "indeed.com"):
        if required not in policy.blocked:
            raise ConfigError(
                f"domain_policy.yaml must keep '{required}' in the blocked list "
                "(the product requirement is that LinkedIn/Indeed are never used for applications)"
            )
    overlap = policy.allowed & policy.blocked
    if overlap:
        raise ConfigError(f"domain_policy.yaml lists domains as both allowed and blocked: {sorted(overlap)}")
    return policy


@dataclass
class AppConfig:
    profile: Profile
    preferences: Preferences
    domain_policy: DomainPolicy
    config_dir: Path
    data_dir: Path


def load_config(
    config_dir: Optional[Path | str] = None, data_dir: Optional[Path | str] = None
) -> AppConfig:
    config_dir = Path(config_dir or DEFAULT_CONFIG_DIR)
    data_dir = Path(data_dir or os.environ.get("JOBAGENT_DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        profile=load_profile(config_dir),
        preferences=load_preferences(config_dir),
        domain_policy=load_domain_policy(config_dir),
        config_dir=config_dir,
        data_dir=data_dir,
    )
