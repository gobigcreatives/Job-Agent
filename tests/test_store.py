import pytest

from jobagent.models import ApplicationResult, JobListing, JobStatus, PendingInput, ScoreBreakdown
from jobagent.tracking.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


def _job(fingerprint="fp1", company="Acme") -> JobListing:
    job = JobListing(source_url="https://x.com/1", title="Role", company=company)
    job.fingerprint = fingerprint
    return job


def test_upsert_and_get_job_status(store):
    job = _job()
    store.upsert_job(job)
    assert store.get_job_status("fp1") == JobStatus.DISCOVERED.value


def test_get_status_by_source_url(store):
    job = _job()
    job.source_url = "https://boards.greenhouse.io/acme/jobs/1?utm_source=google"
    store.upsert_job(job)
    assert store.get_status_by_source_url("https://boards.greenhouse.io/acme/jobs/1?utm_source=google") == JobStatus.DISCOVERED.value
    assert store.get_status_by_source_url("https://unseen.example/x") is None


def test_set_job_status_updates(store):
    job = _job()
    store.upsert_job(job)
    store.set_job_status("fp1", JobStatus.APPLIED)
    assert store.get_job_status("fp1") == JobStatus.APPLIED.value


def test_record_application_and_count_today(store):
    job = _job()
    store.upsert_job(job)
    result = ApplicationResult(job=job, submitted=True, status=JobStatus.APPLIED, score=ScoreBreakdown(total=90))
    store.record_application(result)
    assert store.count_applications_today() == 1
    assert store.count_applications_for_company("Acme") == 1
    assert store.count_applications_for_company("Other") == 0


def test_failed_application_not_counted_toward_limits(store):
    job = _job()
    store.upsert_job(job)
    result = ApplicationResult(job=job, submitted=False, status=JobStatus.FAILED, score=ScoreBreakdown(total=90))
    store.record_application(result)
    assert store.count_applications_today() == 0


def test_pending_input_lifecycle(store):
    pending = PendingInput(job_id="fp1", kind="salary_expectation", question="What's your salary expectation?")
    pending_id = store.add_pending_input(pending)
    unresolved = store.list_pending_inputs(resolved=False)
    assert len(unresolved) == 1
    assert unresolved[0]["id"] == pending_id

    store.resolve_pending_input(pending_id, "GBP 40,000+")
    assert len(store.list_pending_inputs(resolved=False)) == 0
    row = store.get_pending_input(pending_id)
    assert row["answer"] == "GBP 40,000+"


def test_learned_answers_roundtrip(store):
    assert store.get_learned_answer("notice_period") is None
    store.set_learned_answer("notice_period", "2 weeks")
    assert store.get_learned_answer("notice_period") == "2 weeks"
    store.set_learned_answer("notice_period", "1 month")
    assert store.get_learned_answer("notice_period") == "1 month"


def test_query_performance_accumulates_across_runs(store):
    store.record_query_run("query A", jobs_found=10, jobs_matched=3, applications_submitted=1, successful_applications=1)
    store.record_query_run("query A", jobs_found=5, jobs_matched=2, applications_submitted=0, successful_applications=0)
    perf = store.get_query_performance()
    row = perf["query A"]
    assert row["total_jobs_found"] == 15
    assert row["total_jobs_matched"] == 5
    assert row["runs_count"] == 2
