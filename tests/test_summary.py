from datetime import datetime

from jobagent.models import ApplicationResult, JobListing, JobStatus, MatchBand, RunSummary, ScoreBreakdown
from jobagent.reporting.summary import format_summary


def _result(company, title, score):
    job = JobListing(source_url="https://x.com/1", title=title, company=company)
    return ApplicationResult(
        job=job, submitted=True, status=JobStatus.APPLIED,
        score=ScoreBreakdown(total=score, band=MatchBand.STRONG),
    )


def test_format_summary_matches_required_layout():
    summary = RunSummary(
        started_at=datetime.utcnow(),
        jobs_discovered=87, jobs_relevant=24, jobs_skipped=63,
        applications_submitted=12, waiting_for_input=2, manual_verification_required=1, failed=0,
        top_applications=[
            _result("Company A", "Social Media Manager", 94),
            _result("Company B", "Social Media Strategist", 91),
            _result("Company C", "Content Manager", 89),
        ],
    )
    text = format_summary(summary)

    assert "JOB SEARCH SUMMARY" in text
    assert "Jobs discovered: 87" in text
    assert "Relevant jobs: 24" in text
    assert "Skipped: 63" in text
    assert "Applications submitted: 12" in text
    assert "Waiting for input: 2" in text
    assert "Manual verification required: 1" in text
    assert "Failed: 0" in text
    assert "Top applications:" in text
    assert "1. Company A" in text
    assert "   Social Media Manager" in text
    assert "   Match: 94%" in text
    # ranked by score descending regardless of insertion order
    assert text.index("Company A") < text.index("Company B") < text.index("Company C")


def test_format_summary_omits_top_applications_section_when_empty():
    summary = RunSummary(started_at=datetime.utcnow())
    text = format_summary(summary)
    assert "Top applications:" not in text


def test_format_summary_ranks_by_score_not_insertion_order():
    summary = RunSummary(
        started_at=datetime.utcnow(),
        top_applications=[_result("Low", "Role", 60), _result("High", "Role", 95)],
    )
    text = format_summary(summary)
    assert text.index("1. High") < text.index("2. Low")
