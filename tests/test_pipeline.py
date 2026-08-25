from types import SimpleNamespace

import jobagent.pipeline as pipeline_module
from jobagent.models import DomainPolicyStatus, JobStatus, SearchResult
from jobagent.search.providers import SearchProvider
from jobagent.tracking.store import Store

JOB_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Social Media Manager",
  "description": "<p>We need a Social Media Manager with 4 years experience in paid social, content creation, community management and analytics & reporting for our e-commerce and marketing & advertising clients. Hybrid role.</p>",
  "identifier": {"@type": "PropertyValue", "value": "GH-1"},
  "datePosted": "2026-08-01",
  "employmentType": "FULL_TIME",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Co"},
  "jobLocation": {"@type": "Place", "address": {"addressLocality": "London", "addressCountry": "UK"}},
  "baseSalary": {
    "@type": "MonetaryAmount", "currency": "GBP",
    "value": {"@type": "QuantitativeValue", "minValue": 38000, "maxValue": 45000}
  }
}
</script>
</head><body><h1>Social Media Manager</h1></body></html>
"""


class _FixedProvider(SearchProvider):
    def search(self, query, num_results=10):
        return [
            SearchResult(
                query=query, title="Social Media Manager - Acme",
                url="https://boards.greenhouse.io/acme/jobs/1", snippet="Great role at Acme",
            )
        ]


class _EmptyProvider(SearchProvider):
    def search(self, query, num_results=10):
        return []


def _fake_fetch_page(url, session=None, timeout=15):
    return SimpleNamespace(ok=True, status_code=200, url=url, text=JOB_HTML)


def test_dry_run_pipeline_scores_and_previews_without_applying(app_config, monkeypatch, tmp_path):
    store = Store(tmp_path / "pipeline_test.db")
    monkeypatch.setattr(pipeline_module, "fetch_page", _fake_fetch_page)

    summary = pipeline_module.run_cycle(app_config, _FixedProvider(), store, llm=None, apply_enabled=False)

    assert summary.jobs_discovered >= 1
    assert summary.jobs_relevant == 1
    assert summary.jobs_skipped == 0
    assert summary.applications_submitted == 0
    assert len(summary.top_applications) == 1

    previewed = summary.top_applications[0]
    assert previewed.job.company == "Acme Co"
    assert previewed.job.application_url == "https://boards.greenhouse.io/acme/jobs/1"
    assert previewed.job.domain_policy == DomainPolicyStatus.ALLOWED
    assert previewed.score.total >= app_config.preferences.limits.min_match_score
    assert previewed.status == JobStatus.SCORED

    # duplicate results across many queries collapsed to a single job
    assert store.get_job_status(previewed.job.fingerprint) == JobStatus.SCORED.value


def test_second_run_skips_already_terminal_jobs(app_config, monkeypatch, tmp_path):
    store = Store(tmp_path / "pipeline_test2.db")
    monkeypatch.setattr(pipeline_module, "fetch_page", _fake_fetch_page)

    first = pipeline_module.run_cycle(app_config, _FixedProvider(), store, llm=None, apply_enabled=False)
    job_fp = first.top_applications[0].job.fingerprint
    store.set_job_status(job_fp, JobStatus.APPLIED)  # simulate it having gone on to be applied

    second = pipeline_module.run_cycle(app_config, _FixedProvider(), store, llm=None, apply_enabled=False)
    assert second.jobs_relevant == 0
    assert len(second.top_applications) == 0


def test_no_search_results_produces_empty_summary(app_config, tmp_path):
    store = Store(tmp_path / "pipeline_test3.db")
    summary = pipeline_module.run_cycle(app_config, _EmptyProvider(), store, llm=None, apply_enabled=False)
    assert summary.jobs_discovered == 0
    assert summary.jobs_relevant == 0
    assert summary.applications_submitted == 0
