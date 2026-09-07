from jobagent.discovery.extractor import extract_job_details

JSON_LD_PAGE = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Social Media Manager",
  "description": "<p>We need a Social Media Manager with 4 years experience. Fully remote role.</p>",
  "identifier": {"@type": "PropertyValue", "value": "GH-123"},
  "datePosted": "2026-08-01",
  "validThrough": "2026-09-01T00:00:00Z",
  "employmentType": "FULL_TIME",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Co"},
  "jobLocation": {
    "@type": "Place",
    "address": {"addressLocality": "London", "addressCountry": "UK"}
  },
  "baseSalary": {
    "@type": "MonetaryAmount",
    "currency": "GBP",
    "value": {"@type": "QuantitativeValue", "minValue": 38000, "maxValue": 45000, "unitText": "YEAR"}
  }
}
</script>
</head><body><h1>Social Media Manager</h1></body></html>
"""

PLAIN_HTML_PAGE = """
<html><head><title>Content Manager - Acme</title></head>
<body><h1>Content Manager</h1><p>Hybrid role based in London. We need someone great at content.</p></body></html>
"""


def test_extracts_from_json_ld():
    job = extract_job_details("https://boards.greenhouse.io/acme/jobs/123", JSON_LD_PAGE)
    assert job.title == "Social Media Manager"
    assert job.company == "Acme Co"
    assert "London" in job.location
    assert job.external_job_id == "GH-123"
    assert job.employment_type == "full_time"
    assert job.salary_min == 38000
    assert job.salary_max == 45000
    assert job.salary_currency == "GBP"
    assert job.remote_type == "remote"
    assert job.closing_date is not None


def test_falls_back_to_heuristics_without_json_ld():
    job = extract_job_details("https://company.example/careers/content-manager", PLAIN_HTML_PAGE)
    assert "Content Manager" in job.title
    assert len(job.description) > 0
    assert job.remote_type == "hybrid"


def test_heuristic_extracts_company_from_title_suffix():
    job = extract_job_details("https://company.example/careers/content-manager", PLAIN_HTML_PAGE)
    assert job.company == "Acme"


def test_heuristic_prefers_og_site_name_for_company():
    page = """
    <html><head>
    <meta property="og:site_name" content="Beta Widgets Ltd">
    <title>Paid Social Manager | Beta Careers Portal</title>
    </head><body><h1>Paid Social Manager</h1><p>Great role with paid social work.</p></body></html>
    """
    job = extract_job_details("https://beta.example/jobs/1", page)
    assert job.company == "Beta Widgets Ltd"


def test_heuristic_no_company_when_title_has_no_separator():
    page = "<html><head><title>Paid Social Manager</title></head><body><h1>Paid Social Manager</h1><p>x</p></body></html>"
    job = extract_job_details("https://x.example/jobs/1", page)
    assert job.company == ""


def test_heuristic_skips_generic_title_segments():
    page = "<html><head><title>Content Manager - Careers</title></head><body><h1>Content Manager</h1><p>x</p></body></html>"
    job = extract_job_details("https://x.example/jobs/1", page)
    assert job.company == ""
