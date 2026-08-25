# Job Agent

An autonomous job discovery and application agent. You configure a profile
and a set of search preferences once; the agent then finds jobs on Google,
scores them against your preferences, tailors your CV and cover letter, and
applies — without you ever pasting in a job URL. LinkedIn and Indeed are
never used for applications.

```
USER PROFILE
      |
JOB SEARCH PREFERENCES
      v
GENERATE SEARCH QUERIES  ->  SEARCH GOOGLE  ->  COLLECT JOB RESULTS
      v
DEDUPLICATE  ->  EXTRACT JOB DETAILS  ->  IDENTIFY ORIGINAL APPLICATION URL
      v
CHECK DOMAIN POLICY  ->  ANALYSE JOB DESCRIPTION  ->  CALCULATE MATCH SCORE
      v
FILTER OUT POOR MATCHES
      v
TAILOR CV  ->  GENERATE COVER LETTER
      v
OPEN APPLICATION  ->  FILL APPLICATION  ->  HANDLE QUESTIONS  ->  SUBMIT
      v
SEND EMAIL IF APPROPRIATE  ->  TRACK APPLICATION
```

## Setup

```bash
pip install -e ".[dev]"
playwright install chromium   # only needed for the live application step

cp .env.example .env          # fill in API keys — see below
jobagent init                 # scaffolds config/profile.yaml, preferences.yaml, resume.md
```

Edit the three files `jobagent init` creates:

- **`config/profile.yaml`** — who you are: contact details, right-to-work
  statement, skills, experience, base resume path.
- **`config/preferences.yaml`** — what you're looking for: target roles,
  locations, remote preference, salary floor, scoring weights, application
  limits, and search frequency. Everything here is editable without
  touching code.
- **`config/resume.md`** — your real CV content in plain text/Markdown; the
  tailoring step rewrites this per job.

`config/domain_policy.yaml` *is* version-controlled (unlike the two files
above) because it's a safety control, not a personal preference. It hard-
blocks `linkedin.com` and `indeed.com` for applications — the loader
refuses to start if either is removed from the blocked list.

### API keys (`.env`)

| Variable | Used for | Required for |
|---|---|---|
| `GOOGLE_API_KEY`, `GOOGLE_CSE_ID` | Google Programmable Search Engine (Custom Search JSON API) | discovery |
| `GEMINI_API_KEY` **or** `ANTHROPIC_API_KEY` | CV tailoring, cover letters, open-ended question answers | applying |
| `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL` | emailing a hiring contact directly, when a listing asks for that instead of a form | the rare email-apply path |

**Google Search setup** — two separate things, both free:
1. Create a search engine at https://programmablesearchengine.google.com/
   and turn its **"Search the entire web"** control ON (not restricted to
   specific sites — restricting it defeats the point of discovering
   arbitrary company career pages). Copy its **Search engine ID** into
   `GOOGLE_CSE_ID`.
2. Create an API key at https://console.cloud.google.com/apis/credentials
   -> **Create Credentials -> API key**. On the key's settings page, under
   **"Select API restrictions"**, choose **Custom Search API** from the
   dropdown (search for it if it's not listed yet) and save — that's the
   only API this key needs access to. Copy the key into `GOOGLE_API_KEY`.
   Free tier: 100 searches/day; beyond that it's billed per query, so this
   is the one piece with a usage-based cost if you run a very high search
   volume.

**LLM setup — no paid API required.** By default use **Gemini**, which is
free with no credit card: get a key at https://aistudio.google.com/apikey
and set `GEMINI_API_KEY`. The free tier's daily quota comfortably covers a
personal job search's volume of CV/cover-letter generations. Only set
`ANTHROPIC_API_KEY` instead if you'd specifically rather pay for Claude —
whichever variable is set is used automatically.

## Usage

```bash
jobagent run --dry-run   # discover + score jobs, print what WOULD be applied to — nothing is submitted
jobagent run             # full autonomous cycle: discover, score, tailor, apply
jobagent report          # reprint the last run's summary
jobagent pending         # list application questions waiting on you
jobagent answer 7 "..."  # answer one — and it's remembered for every future application of that kind
jobagent schedule        # print the cron expression for your configured search frequency
```

Run `--dry-run` first. It exercises the entire discovery and scoring
pipeline against real search results with nothing held back — you'll see
exactly which jobs it found and how they scored — but stops before
tailoring a CV or touching a browser, so there is no cost and nothing is
submitted while you're checking the match quality is sane.

### Scheduling

`jobagent run` is a single-shot command by design — point your own
scheduler at it rather than relying on a long-lived process, so search
frequency survives container/server restarts:

```bash
jobagent schedule
# frequency: every_6_hours
# cron (UTC): 0 */6 * * *
# next run (UTC): 2026-08-25T18:00:00+00:00
```

Wire that cron expression into OS cron, a systemd timer, or a platform
scheduler (e.g. this repo's `create_trigger`/Routines tooling, if you're
running this inside Claude Code). `schedule.frequency` in
`preferences.yaml` accepts `manual`, `hourly`, `every_6_hours`, or
`daily_morning` (with a configurable `run_time`/`timezone`).

## How autonomy works

- **Search queries are generated, not written by you.** `jobagent.search.query_builder`
  fans a single profile out into dozens of Google queries: role x location,
  role x remote preference, seniority-qualified variants, skill-anchored
  variants, industry-anchored variants, employment-type variants, and
  queries restricted to known ATS domains (`site:boards.greenhouse.io OR
  site:jobs.lever.co OR ...`) that tend to land directly on the original
  application page. `jobagent.learning` tracks which queries actually
  produce matched/applied-to jobs over time and biases future runs toward
  them, without ever trying to route around a search engine's own limits.

- **The original application URL is preferred over aggregators.**
  `jobagent.discovery.url_resolver` looks for an "Apply"-labelled link (or
  canonical/og:url) pointing to a pre-approved domain before falling back
  to whatever Google returned.

- **A hard domain policy gates every application.**
  `config/domain_policy.yaml` classifies every application URL as
  `ALLOWED` / `BLOCKED` / `MANUAL_REVIEW`. Unknown domains default to
  `MANUAL_REVIEW`, never to auto-apply. LinkedIn and Indeed are
  permanently `BLOCKED`.

- **Duplicates are recognised across sources.** The same vacancy showing up
  on Google, a job board, and the company's own site collapses into one
  record — matched by external job id, canonical URL, or company+title+
  location+description similarity (`jobagent.dedup`).

- **Match scoring is weighted and configurable.** Skills, experience, role,
  location, industry, salary, and other preferences each contribute a
  0-100 sub-score; the weighted total is banded into
  Excellent/Strong/Potential/Skip using the cutoffs in `preferences.yaml`.
  Only jobs at or above `scoring.auto_apply_min_score` are auto-applied to.

- **Applications respect strict limits.** Per-day, per-hour, and
  per-company caps in `preferences.yaml` are enforced against the
  application history in the local SQLite store — the run stops applying
  once a limit is hit, regardless of how many more strong matches remain.

- **Forms are filled without vendor-specific selectors.** Rather than
  hardcoding CSS selectors per ATS (which drift constantly),
  `jobagent.application.generic_filler` walks the live form's DOM, computes
  each field's accessible label the way a screen reader would, and
  classifies it the same way free-text application questions are
  classified. That means it isn't tied to Greenhouse/Lever/Workday's
  current markup, at the cost of occasionally missing an unusually-marked
  field — which is exactly the case designed to escalate rather than
  guess.

- **You're only asked what the agent can't determine itself.** Standard
  questions (work authorisation, salary expectation, notice period,
  relocation, LinkedIn/portfolio URL, "why do you want to work here") are
  answered from `profile.yaml`/`preferences.yaml` or generated by the LLM
  from the job description — never invented from nothing. A genuinely
  ambiguous question, a CAPTCHA, or an application domain outside the
  pre-approved policy creates a **pending input**
  (`jobagent pending` / `jobagent answer`). Once you answer a *kind* of
  question once, it's remembered and reused for every later application —
  you're never asked the same category of question twice.

## Safety by design

- `linkedin.com` and `indeed.com` are hard-blocked; the config loader
  refuses to start if they're removed from `domain_policy.yaml`.
- Unknown application domains default to manual review, not auto-apply.
- Daily/hourly/per-company application caps are enforced from persisted
  history, not just in-memory counters, so they hold across runs.
- Search results are cached (`search.cache_ttl_hours`) and rate-limited
  (`search.request_delay_seconds`) to avoid excessive query traffic.
- A listing is checked for real-vacancy signals (closing date, "position
  filled" language, HTTP status) before it's scored or applied to.
- CV tailoring and cover letter generation are explicitly instructed never
  to invent employers, dates, or skills not present in your base resume.

## Project layout

```
config/                   profile/preferences/domain-policy YAML (see Setup)
src/jobagent/
  config.py, models.py     config loading + shared data structures
  search/                  query generation, Google Custom Search provider, cache
  discovery/               page fetch, JSON-LD/heuristic extraction, URL resolution, expiry checks
  domain_policy/           ALLOWED/BLOCKED/MANUAL_REVIEW classification
  dedup/                   cross-source duplicate detection
  scoring/                 weighted match scoring
  generation/               LLM-backed CV tailoring + cover letters
  application/              Playwright browser, generic form filler, question bank, apply runner
  tracking/                  SQLite store: jobs, applications, pending inputs, learned answers, query stats
  learning/                  query-performance-based prioritisation
  reporting/                  end-of-run summary formatting
  scheduling/                 cron expression / next-run-time helpers
  notifications/              apply-by-email fallback
  pipeline.py, cli.py         orchestration + CLI
tests/                     unit tests for all of the above (no network required)
```

## Testing

```bash
pytest
```

The full suite (100+ tests) runs offline and covers every piece of pure
logic: config validation, query generation, domain policy, deduplication,
match scoring, question classification/answering, form-fill decisioning,
the tracking store, query-performance ranking, scheduling math, and the
pipeline orchestration end-to-end against a mocked search provider and
fetched page.

What it deliberately does **not** cover, because doing so needs live
credentials and real third-party sites: actually calling the Google Custom
Search API, calling the Anthropic API, and driving a real browser against
a real ATS's current markup. Those integration points (`GoogleCustomSearchProvider`,
`LLMClient`, `jobagent.application.runner`/`browser.py`) are written
against each service's real interface and are exercised by the unit tests
only through fakes/mocks — validate them against a live job posting or two
with real API keys before trusting `jobagent run` unattended.

## Known limitations

- Resume/cover letter files are generated as plain text, not a formatted
  PDF/DOCX. Most ATS accept `.txt`; if a listing strictly requires PDF,
  that upload will need a rendering step added on top (e.g. via a DOCX/PDF
  templating library).
- The generic form filler handles text/email/tel/textarea, `<select>`,
  and grouped radio/checkbox questions, plus file uploads for resume/cover
  letter. A field marked up in some other way is escalated rather than
  guessed at — check `jobagent pending` after a run.
- `daily_morning` scheduling computes a UTC cron expression once, at the
  moment you run `jobagent schedule`; if your timezone observes daylight
  saving, re-run it after a DST transition to keep the UTC hour correct.
