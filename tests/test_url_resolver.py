from jobagent.discovery.url_resolver import find_candidate_application_links, resolve_application_url
from jobagent.models import DomainPolicyStatus


AGGREGATOR_PAGE = """
<html><body>
<h1>Social Media Manager at Acme</h1>
<p>Great role. <a href="https://boards.greenhouse.io/acme/jobs/999">Apply Now</a></p>
<a href="/other-jobs">See other jobs</a>
</body></html>
"""

DIRECT_ATS_PAGE = "<html><body><h1>Already on the ATS</h1></body></html>"


def test_already_on_allowed_domain_is_returned_as_is(domain_policy):
    url = resolve_application_url("https://boards.greenhouse.io/acme/jobs/1", DIRECT_ATS_PAGE, domain_policy)
    assert url == "https://boards.greenhouse.io/acme/jobs/1"


def test_finds_apply_link_pointing_to_allowed_domain(domain_policy):
    url = resolve_application_url("https://aggregator.example/listing/1", AGGREGATOR_PAGE, domain_policy)
    assert url == "https://boards.greenhouse.io/acme/jobs/999"


def test_falls_back_to_original_url_when_no_allowed_link_found(domain_policy):
    page = "<html><body><a href='https://another-aggregator.example/x'>Apply</a></body></html>"
    url = resolve_application_url("https://aggregator.example/listing/1", page, domain_policy)
    assert url == "https://aggregator.example/listing/1"


def test_find_candidate_application_links_resolves_relative_urls():
    page = "<a href='/apply/here'>Apply</a>"
    links = find_candidate_application_links(page, "https://company.example/jobs/1")
    assert "https://company.example/apply/here" in links


def test_canonical_link_is_a_candidate():
    page = '<link rel="canonical" href="https://boards.greenhouse.io/acme/jobs/999">'
    links = find_candidate_application_links(page, "https://aggregator.example/x")
    assert "https://boards.greenhouse.io/acme/jobs/999" in links
