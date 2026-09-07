from datetime import datetime, timedelta

from jobagent.discovery.validator import is_still_open
from jobagent.models import JobListing


def _job(**overrides) -> JobListing:
    defaults = dict(
        source_url="https://x.com/1",
        title="Social Media Manager",
        description="A" * 200,
    )
    defaults.update(overrides)
    return JobListing(**defaults)


def test_normal_open_job_is_open():
    assert is_still_open(_job()) is True


def test_http_error_status_is_not_open():
    assert is_still_open(_job(), http_status=404) is False


def test_expired_closing_date_is_not_open():
    job = _job(closing_date=datetime.utcnow() - timedelta(days=5))
    assert is_still_open(job) is False


def test_future_closing_date_is_open():
    job = _job(closing_date=datetime.utcnow() + timedelta(days=5))
    assert is_still_open(job) is True


def test_expired_phrase_in_description_is_not_open():
    job = _job(description="A" * 200 + " This position has been filled.")
    assert is_still_open(job) is False


def test_too_short_to_be_a_real_vacancy():
    job = _job(title="", description="short")
    assert is_still_open(job) is False


def test_rejects_numbered_listing_page_title():
    job = _job(title="816 Digital marketing executive jobs in United Kingdom")
    assert is_still_open(job) is False


def test_rejects_numbered_listing_page_title_with_comma():
    job = _job(title="1,548 Social media manager jobs in United Kingdom")
    assert is_still_open(job) is False


def test_rejects_listing_page_title_without_leading_number():
    job = _job(title="Digital Marketing Executive jobs in Remote")
    assert is_still_open(job) is False


def test_rejects_search_results_title():
    job = _job(title="Search Results - Social Media Manager")
    assert is_still_open(job) is False


def test_accepts_real_single_job_title_with_location_suffix():
    # A genuine single-vacancy title, singular "Manager" — not "jobs" —
    # must not be caught by the listing-page filter.
    job = _job(title="Social Media Manager - London")
    assert is_still_open(job) is True


def test_accepts_real_single_job_title_with_number_in_it():
    # A job req/reference number prefix shouldn't be confused with a
    # listing page's job count.
    job = _job(title="REQ-4021 Social Media Manager")
    assert is_still_open(job) is True
