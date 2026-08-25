from jobagent.domain_policy.policy import classify_domain, classify_url
from jobagent.models import DomainPolicyStatus


def test_linkedin_is_blocked(domain_policy):
    assert classify_url("https://www.linkedin.com/jobs/view/12345", domain_policy) == DomainPolicyStatus.BLOCKED


def test_indeed_is_blocked(domain_policy):
    assert classify_url("https://uk.indeed.com/viewjob?jk=abc", domain_policy) == DomainPolicyStatus.BLOCKED


def test_known_ats_is_allowed(domain_policy):
    assert classify_url("https://boards.greenhouse.io/acme/jobs/123", domain_policy) == DomainPolicyStatus.ALLOWED


def test_subdomain_matches_parent_policy_entry(domain_policy):
    assert classify_domain("careers.myworkdayjobs.com", domain_policy) == DomainPolicyStatus.ALLOWED


def test_unrelated_domain_similar_to_blocked_is_not_blocked(domain_policy):
    # "notlinkedin.com" must not match a blocked-list entry for "linkedin.com"
    assert classify_domain("notlinkedin.com", domain_policy) != DomainPolicyStatus.BLOCKED


def test_manual_review_domain(domain_policy):
    assert classify_domain("glassdoor.com", domain_policy) == DomainPolicyStatus.MANUAL_REVIEW


def test_unknown_domain_falls_back_to_default_policy(domain_policy):
    assert classify_domain("some-random-startup-careers.example", domain_policy) == DomainPolicyStatus.MANUAL_REVIEW


def test_blocked_takes_precedence_if_domain_somehow_in_both():
    from jobagent.config import DomainPolicy

    policy = DomainPolicy(blocked={"x.com"}, allowed={"x.com"}, manual_review=set(), default_policy="manual_review")
    assert classify_domain("x.com", policy) == DomainPolicyStatus.BLOCKED
