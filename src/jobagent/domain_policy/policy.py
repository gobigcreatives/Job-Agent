"""ALLOWED / BLOCKED / MANUAL_REVIEW classification for application URLs.

This is the hard safety boundary: it is the only thing standing between "the
agent found a plausible-looking application form" and "the agent actually
submits an application through it". Matching is by registrable domain and
subdomain suffix, so `boards.greenhouse.io` matches a policy entry for
`greenhouse.io`, but `notgreenhouse.io` does not.
"""
from __future__ import annotations

from urllib.parse import urlparse

from jobagent.config import DomainPolicy
from jobagent.models import DomainPolicyStatus


def _host(url_or_domain: str) -> str:
    if "//" in url_or_domain:
        host = urlparse(url_or_domain).netloc
    else:
        host = url_or_domain
    host = host.lower().split(":")[0]
    return host.removeprefix("www.")


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def classify_domain(host: str, policy: DomainPolicy) -> DomainPolicyStatus:
    host = _host(host)
    if any(_matches(host, d) for d in policy.blocked):
        return DomainPolicyStatus.BLOCKED
    if any(_matches(host, d) for d in policy.allowed):
        return DomainPolicyStatus.ALLOWED
    if any(_matches(host, d) for d in policy.manual_review):
        return DomainPolicyStatus.MANUAL_REVIEW
    return DomainPolicyStatus(
        {
            "allowed": "ALLOWED",
            "blocked": "BLOCKED",
            "manual_review": "MANUAL_REVIEW",
        }[policy.default_policy]
    )


def classify_url(url: str, policy: DomainPolicy) -> DomainPolicyStatus:
    return classify_domain(_host(url), policy)
