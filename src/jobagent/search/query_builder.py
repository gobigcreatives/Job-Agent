"""Turns a profile + preferences into concrete Google search queries
(requirement #1). Never issues a single generic query — it fans out across
role x location x seniority x skill combinations, plus a set of queries
restricted to known ATS domains so the discovery pipeline lands closer to
the original company application page instead of an aggregator.

LinkedIn and Indeed are excluded from every generated query: the product
requirement is that they're never used for applications, and since we'd
throw away any result on those domains anyway (see domain_policy), there's
no reason to spend query budget surfacing them.
"""
from __future__ import annotations

from jobagent.config import Preferences, Profile

_EXCLUDED_SITES = ["linkedin.com", "indeed.com", "indeed.co.uk"]

# A curated subset of major ATS platforms, used to build queries that search
# only within known-good application domains (site:a.com OR site:b.com ...).
# Kept short deliberately — most search engines only honour the first
# several OR'd site: clauses reliably.
_ATS_SITES_FOR_SEARCH = [
    "boards.greenhouse.io",
    "jobs.lever.co",
    "myworkdayjobs.com",
    "jobs.ashbyhq.com",
    "apply.workable.com",
    "smartrecruiters.com",
]


def _exclusions() -> str:
    return " ".join(f"-site:{site}" for site in _EXCLUDED_SITES)


def _ats_site_filter() -> str:
    return "(" + " OR ".join(f"site:{site}" for site in _ATS_SITES_FOR_SEARCH) + ")"


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        normalized = " ".join(item.split())
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def generate_queries(profile: Profile, preferences: Preferences) -> list[str]:
    """Returns every candidate query, most-targeted first. Callers (the
    pipeline, via jobagent.learning) are expected to cap this to
    preferences.search.max_queries_per_run, optionally reordered by
    historical yield."""
    queries: list[str] = []
    exclusions = _exclusions()
    roles = preferences.target_roles
    locations = preferences.locations
    remote_locations = [loc for loc in locations if "remote" in loc.lower()]
    onsite_locations = [loc for loc in locations if "remote" not in loc.lower()]

    # 1. Core role x location — the bread and butter, e.g.
    #    "social media manager" jobs London
    for role in roles:
        for location in onsite_locations:
            queries.append(f'"{role}" jobs {location} {exclusions}')

    # 2. Role x remote preference, e.g. "social media manager" remote UK
    for role in roles:
        for location in remote_locations:
            queries.append(f'"{role}" {location} {exclusions}')
        if "remote" in [r.lower() for r in preferences.remote_accepted]:
            base_region = onsite_locations[0] if onsite_locations else ""
            queries.append(f'"{role}" remote {base_region} {exclusions}'.strip())

    # 3. Seniority-qualified role, e.g. "Manager Social Media Manager" ->
    #    skip if seniority already appears in the role name.
    if profile.seniority:
        for role in roles:
            if profile.seniority.lower() not in role.lower():
                for location in onsite_locations[:2]:
                    queries.append(f'"{profile.seniority} {role}" jobs {location} {exclusions}')

    # 4. Skill-anchored queries — surfaces roles titled differently but
    #    requiring a specific in-demand skill, e.g.
    #    "paid social" "manager" jobs London
    for skill in profile.skills[:6]:
        for location in onsite_locations[:2]:
            queries.append(f'"{skill}" jobs {location} {exclusions}')

    # 5. Industry-anchored queries, e.g. "social media manager" "e-commerce" London
    for industry in preferences.industries[:4]:
        for role in roles[:3]:
            queries.append(f'"{role}" "{industry}" jobs {exclusions}')

    # 6. Employment-type-anchored queries, e.g. "social media manager" freelance UK
    for employment_type in preferences.employment_types:
        if employment_type == "full_time":
            continue
        label = employment_type.replace("_", " ")
        for role in roles[:3]:
            location = onsite_locations[0] if onsite_locations else ""
            queries.append(f'"{role}" {label} {location} {exclusions}'.strip())

    # 7. Careers-page-anchored queries — biases toward company sites rather
    #    than job boards.
    for role in roles[:4]:
        for location in onsite_locations[:2]:
            queries.append(f'"{role}" careers "apply" {location} {exclusions}')

    # 8. ATS-restricted queries — searches only within known application
    #    platforms, which tends to land directly on the original
    #    application form.
    for role in roles[:4]:
        queries.append(f'"{role}" {_ats_site_filter()}')

    return _dedupe_preserve_order(queries)
