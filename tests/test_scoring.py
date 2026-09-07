from jobagent.models import JobListing, MatchBand
from jobagent.scoring.matcher import _skill_fragments, _skills_match, score_job


def _job(**overrides) -> JobListing:
    defaults = dict(
        source_url="https://boards.greenhouse.io/acme/jobs/123",
        title="Social Media Manager",
        company="Acme Co",
        location="London, UK",
        description=(
            "We're looking for a Social Media Manager with 4 years experience "
            "in paid social, content creation, and analytics & reporting for "
            "our e-commerce brand. Marketing & Advertising background a plus."
        ),
        remote_type="hybrid",
        employment_type="full_time",
        salary_min=38000,
        salary_max=45000,
        salary_currency="GBP",
    )
    defaults.update(overrides)
    return JobListing(**defaults)


def test_strong_match_scores_highly(profile, preferences):
    job = _job()
    result = score_job(job, profile, preferences)
    assert result.total >= 70
    assert result.band in (MatchBand.STRONG, MatchBand.EXCELLENT, MatchBand.POTENTIAL)


def test_excluded_company_forces_skip(profile, preferences):
    job = _job(company="Bad Co")
    result = score_job(job, profile, preferences)
    assert result.total == 0
    assert result.band == MatchBand.SKIP


def test_excluded_role_forces_skip(profile, preferences):
    job = _job(title="Sales Executive")
    result = score_job(job, profile, preferences)
    assert result.total == 0
    assert result.band == MatchBand.SKIP


def test_unrelated_role_scores_lower_than_target_role(profile, preferences):
    matched = score_job(_job(title="Social Media Manager"), profile, preferences)
    unrelated = score_job(_job(title="Backend Software Engineer", description="Python, Kubernetes, distributed systems, 5 years experience."), profile, preferences)
    assert matched.total > unrelated.total


def test_salary_below_minimum_reduces_score(profile, preferences):
    good = score_job(_job(salary_min=40000, salary_max=45000), profile, preferences)
    low = score_job(_job(salary_min=18000, salary_max=20000), profile, preferences)
    assert good.salary_match > low.salary_match
    assert good.total > low.total


def test_missing_salary_is_neutral_not_punished_to_zero(profile, preferences):
    result = score_job(_job(salary_min=None, salary_max=None), profile, preferences)
    assert result.salary_match > 0


def test_weights_are_applied(profile, preferences):
    job = _job()
    result = score_job(job, profile, preferences)
    weights = preferences.scoring.weights
    expected_total = round(
        sum(getattr(result, factor) * weight for factor, weight in weights.items()), 1
    )
    assert result.total == expected_total


def test_skill_fragments_splits_compound_phrase():
    fragments = _skill_fragments("Paid social (Meta Ads, LinkedIn Ads, Twitter/X Ads, Google Ads)")
    assert "paid social" in fragments or "Paid social" in fragments
    assert "Meta Ads" in fragments
    assert "LinkedIn Ads" in fragments
    assert "Google Ads" in fragments


def test_skill_fragments_splits_ampersand():
    fragments = _skill_fragments("Analytics & reporting")
    assert "Analytics" in fragments
    assert "reporting" in fragments


def test_skills_match_hits_on_partial_compound_skill(profile):
    from jobagent.config import Profile

    compound_profile = Profile(
        name="Test", email="t@example.com", phone="0", location="London",
        work_authorization="x", resume_text_path="x",
        skills=["Paid social (Meta Ads, LinkedIn Ads, Twitter/X Ads, Google Ads)"],
    )
    job_with_fragment_only = JobListing(
        source_url="https://x.com/1", title="Role",
        description="We need someone experienced running Meta Ads campaigns daily.",
    )
    # Old behaviour required the *entire* compound phrase verbatim in the
    # description, which real job postings never contain — this is the bug
    # that caused every real job to score near-zero on skills.
    assert _skills_match(job_with_fragment_only, compound_profile) > 0


def test_band_thresholds(profile, preferences):
    job = _job()
    result = score_job(job, profile, preferences)
    bands = preferences.scoring.bands
    if result.total >= bands["excellent"]:
        assert result.band == MatchBand.EXCELLENT
    elif result.total >= bands["strong"]:
        assert result.band == MatchBand.STRONG
    elif result.total >= bands["potential"]:
        assert result.band == MatchBand.POTENTIAL
    else:
        assert result.band == MatchBand.SKIP
