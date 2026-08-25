from jobagent.dedup.deduplicator import canonical_url, compute_fingerprint, deduplicate
from jobagent.models import JobListing


def test_exact_duplicate_urls_merge():
    long_description = "A" * 250
    a = JobListing(
        source_url="https://boards.greenhouse.io/acme/jobs/123?utm_source=google",
        title="Social Media Manager", company="Acme", location="London", description=long_description,
    )
    b = JobListing(
        source_url="https://boards.greenhouse.io/acme/jobs/123?utm_source=indeed&utm_medium=cpc",
        title="Social Media Manager", company="Acme", location="London", description=long_description,
    )
    result = deduplicate([a, b])
    assert len(result) == 1


def test_same_external_job_id_merges_even_with_different_urls():
    a = JobListing(source_url="https://boardsite-a.com/job/1", external_job_id="GH-42", title="X", company="Acme")
    b = JobListing(source_url="https://boardsite-b.com/mirror/1", external_job_id="GH-42", title="X", company="Acme")
    result = deduplicate([a, b])
    assert len(result) == 1


def test_similar_titles_same_company_location_merge():
    a = JobListing(source_url="https://a.com/1", title="Social Media Manager", company="Acme Co", location="London")
    b = JobListing(source_url="https://b.com/1", title="Social Media Manager ", company="Acme Co", location="London")
    result = deduplicate([a, b])
    assert len(result) == 1


def test_different_companies_do_not_merge():
    a = JobListing(source_url="https://a.com/1", title="Social Media Manager", company="Acme Co", location="London")
    b = JobListing(source_url="https://b.com/1", title="Social Media Manager", company="Widget Inc", location="London")
    result = deduplicate([a, b])
    assert len(result) == 2


def test_near_identical_descriptions_merge_despite_different_titles():
    description = "We are hiring a social media manager to run paid and organic social. " * 5
    a = JobListing(source_url="https://a.com/1", title="Social Media Manager", company="", description=description)
    b = JobListing(source_url="https://b.com/1", title="Social Media Lead", company="", description=description)
    result = deduplicate([a, b])
    assert len(result) == 1


def test_merge_keeps_richest_record():
    short = JobListing(source_url="https://a.com/1", external_job_id="X1", title="Role", company="Acme", description="short")
    rich = JobListing(
        source_url="https://a.com/1", external_job_id="X1", title="Role", company="Acme",
        description="A" * 500, application_url="https://boards.greenhouse.io/acme/jobs/1",
    )
    result = deduplicate([short, rich])
    assert len(result) == 1
    assert result[0].application_url == "https://boards.greenhouse.io/acme/jobs/1"


def test_canonical_url_strips_tracking_params():
    assert canonical_url("https://x.com/job/1?utm_source=a&gh_src=b&real=1") == "https://x.com/job/1?real=1"


def test_canonical_url_strips_trailing_slash_and_www():
    assert canonical_url("https://www.x.com/job/1/") == canonical_url("https://x.com/job/1")


def test_fingerprint_is_stable_for_same_input():
    job = JobListing(source_url="https://a.com/1", title="Role", company="Acme", location="London")
    assert compute_fingerprint(job) == compute_fingerprint(job)


def test_transitive_merging_across_a_chain():
    # a<->b share company/location/title, b<->c share description — a and c
    # should end up in the same group even though they don't directly match.
    description = "We are hiring a paid social manager for our retail brand. " * 5
    a = JobListing(source_url="https://a.com/1", title="Paid Social Manager", company="Acme", location="London", description="short a")
    b = JobListing(source_url="https://b.com/1", title="Paid Social Manager", company="Acme", location="London", description=description)
    c = JobListing(source_url="https://c.com/1", title="Totally Different Title", company="Other Co", location="Remote", description=description)
    result = deduplicate([a, b, c])
    assert len(result) == 1
