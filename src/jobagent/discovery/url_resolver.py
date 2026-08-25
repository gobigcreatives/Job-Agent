"""Resolves the *original* application URL for a listing (requirement #10).

Google frequently surfaces a third-party mirror of a vacancy rather than the
company's own posting. The priority order, matching the spec:
  1. The page we already landed on, if its domain is already an approved
     ATS/company domain.
  2. An "Apply"-labelled link on the page that points to an approved domain.
  3. The page's canonical URL / og:url, if that points to an approved
     domain.
  4. Otherwise, the page itself — left for the domain policy check to route
     to BLOCKED or MANUAL_REVIEW rather than guessing.

This module never fabricates a URL; it only picks among links actually
present on the fetched page.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobagent.config import DomainPolicy
from jobagent.domain_policy import classify_url
from jobagent.models import DomainPolicyStatus

_APPLY_PATTERN = re.compile(r"\bapply\b|\bapply now\b|\bview job\b|\bsee job\b", re.IGNORECASE)


def find_candidate_application_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if _APPLY_PATTERN.search(text) or _APPLY_PATTERN.search(href):
            candidates.append(urljoin(base_url, href))

    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        candidates.append(urljoin(base_url, canonical["href"]))

    og_url = soup.find("meta", attrs={"property": "og:url"})
    if og_url and og_url.get("content"):
        candidates.append(urljoin(base_url, og_url["content"]))

    return candidates


def resolve_application_url(final_url: str, html: str, domain_policy: DomainPolicy) -> str:
    if classify_url(final_url, domain_policy) == DomainPolicyStatus.ALLOWED:
        return final_url

    for candidate in find_candidate_application_links(html, final_url):
        if classify_url(candidate, domain_policy) == DomainPolicyStatus.ALLOWED:
            return candidate

    return final_url
