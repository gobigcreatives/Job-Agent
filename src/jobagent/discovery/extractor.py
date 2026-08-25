"""Fetches a job listing page and extracts structured details from it.

Preference order:
  1. schema.org JobPosting JSON-LD (`<script type="application/ld+json">`).
     This is what almost every ATS (Greenhouse, Lever, Workday, Workable,
     Ashby, ...) and most job boards embed for SEO, and it's structured
     data rather than something we have to guess at — by far the most
     reliable signal available without a headless browser.
  2. HTML heuristics (title tag, meta description, common ATS DOM patterns)
     as a fallback when no JobPosting JSON-LD is present.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from jobagent.models import JobListing

logger = logging.getLogger(__name__)

USER_AGENT = "JobAgent/0.1 (+autonomous job-search assistant; respects robots.txt)"

_EMPLOYMENT_TYPE_MAP = {
    "FULL_TIME": "full_time",
    "PART_TIME": "part_time",
    "CONTRACTOR": "contract",
    "TEMPORARY": "contract",
    "INTERN": "internship",
    "VOLUNTEER": "volunteer",
    "PER_DIEM": "contract",
    "OTHER": "full_time",
}

_REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)
_HYBRID_PATTERN = re.compile(r"\bhybrid\b", re.IGNORECASE)


def fetch_page(url: str, session: requests.Session | None = None, timeout: float = 15) -> requests.Response:
    session = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    return session.get(url, headers=headers, timeout=timeout, allow_redirects=True)


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_job_postings(soup: BeautifulSoup) -> list[dict]:
    postings = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict):
                graph = candidate.get("@graph")
                nested = graph if isinstance(graph, list) else [candidate]
                for item in nested:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        postings.append(item)
    return postings


def _from_json_ld(posting: dict, url: str) -> JobListing:
    org = posting.get("hiringOrganization") or {}
    location_obj = posting.get("jobLocation") or {}
    if isinstance(location_obj, list):
        location_obj = location_obj[0] if location_obj else {}
    address = location_obj.get("address") or {} if isinstance(location_obj, dict) else {}
    location_parts = [
        address.get("addressLocality") if isinstance(address, dict) else None,
        address.get("addressRegion") if isinstance(address, dict) else None,
        address.get("addressCountry") if isinstance(address, dict) else None,
    ]
    location = ", ".join(p for p in location_parts if p) or (
        address if isinstance(address, str) else ""
    )

    salary = posting.get("baseSalary") or {}
    salary_value = salary.get("value") if isinstance(salary, dict) else {}
    salary_min = salary_max = None
    salary_currency = salary.get("currency") if isinstance(salary, dict) else None
    if isinstance(salary_value, dict):
        salary_min = salary_value.get("minValue")
        salary_max = salary_value.get("maxValue")
        if salary_value.get("value") is not None and salary_min is None:
            salary_min = salary_max = salary_value.get("value")

    is_remote = bool(posting.get("jobLocationType") == "TELECOMMUTE") or bool(
        posting.get("applicantLocationRequirements")
    )
    description_text = _strip_html(posting.get("description", ""))
    remote_type = None
    if is_remote or _REMOTE_PATTERN.search(description_text[:2000]):
        remote_type = "remote"
    elif _HYBRID_PATTERN.search(description_text[:2000]):
        remote_type = "hybrid"
    else:
        remote_type = "office"

    employment_type_raw = posting.get("employmentType")
    if isinstance(employment_type_raw, list):
        employment_type_raw = employment_type_raw[0] if employment_type_raw else None
    employment_type = _EMPLOYMENT_TYPE_MAP.get((employment_type_raw or "").upper(), None)
    if employment_type is None and "freelance" in description_text.lower():
        employment_type = "freelance"

    return JobListing(
        source_url=url,
        title=posting.get("title", "").strip(),
        company=(org.get("name") if isinstance(org, dict) else "") or "",
        location=location,
        description=description_text,
        external_job_id=str(
            (posting.get("identifier") or {}).get("value", "") if isinstance(posting.get("identifier"), dict) else ""
        ),
        closing_date=_parse_date(posting.get("validThrough")),
        posted_date=_parse_date(posting.get("datePosted")),
        remote_type=remote_type,
        employment_type=employment_type,
        salary_min=float(salary_min) if salary_min else None,
        salary_max=float(salary_max) if salary_max else None,
        salary_currency=salary_currency,
    )


def _from_heuristics(soup: BeautifulSoup, url: str) -> JobListing:
    title_tag = soup.find(["h1"]) or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    description = _strip_html(str(soup.find("body"))) if soup.find("body") else ""
    if not description and meta_desc:
        description = meta_desc.get("content", "")

    remote_type = "office"
    if _REMOTE_PATTERN.search(description[:3000]):
        remote_type = "remote"
    elif _HYBRID_PATTERN.search(description[:3000]):
        remote_type = "hybrid"

    return JobListing(
        source_url=url,
        title=title,
        description=description[:20000],
        remote_type=remote_type,
    )


def extract_job_details(url: str, html: str) -> JobListing:
    soup = BeautifulSoup(html, "html.parser")
    postings = _find_job_postings(soup)
    if postings:
        job = _from_json_ld(postings[0], url)
    else:
        job = _from_heuristics(soup, url)
    if not job.description:
        job.description = _strip_html(html)[:20000]
    return job
