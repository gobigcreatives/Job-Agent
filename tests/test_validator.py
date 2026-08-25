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
