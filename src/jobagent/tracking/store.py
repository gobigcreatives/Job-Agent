"""SQLite-backed persistence for everything the pipeline needs to remember
between runs: which jobs have been seen (for dedup across runs, not just
within one), applications submitted (for limits + the summary report),
questions waiting on the user, and search query performance (for the
learning module).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jobagent.models import (
    ApplicationResult,
    DomainPolicyStatus,
    JobListing,
    JobStatus,
    PendingInput,
    RunSummary,
    ScoreBreakdown,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    location TEXT,
    source_url TEXT,
    application_url TEXT,
    external_job_id TEXT,
    domain_policy TEXT,
    status TEXT,
    match_score REAL,
    score_breakdown_json TEXT,
    discovered_via_query TEXT,
    discovered_at TEXT,
    closing_date TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_fingerprint TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    resume_path TEXT,
    cover_letter_path TEXT,
    status TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (job_fingerprint) REFERENCES jobs (fingerprint)
);

CREATE TABLE IF NOT EXISTS pending_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_fingerprint TEXT NOT NULL,
    kind TEXT NOT NULL,
    question TEXT NOT NULL,
    context TEXT,
    created_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    answer TEXT,
    FOREIGN KEY (job_fingerprint) REFERENCES jobs (fingerprint)
);

CREATE TABLE IF NOT EXISTS search_queries (
    query TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL,
    last_run_at TEXT,
    runs_count INTEGER NOT NULL DEFAULT 0,
    total_jobs_found INTEGER NOT NULL DEFAULT 0,
    total_jobs_matched INTEGER NOT NULL DEFAULT 0,
    total_applications_submitted INTEGER NOT NULL DEFAULT 0,
    total_successful_applications INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary_json TEXT
);

-- Answers the user has given once to a *category* of question (e.g.
-- "salary_expectation"), reused automatically on every later application so
-- the same question is never asked twice.
CREATE TABLE IF NOT EXISTS learned_answers (
    kind TEXT PRIMARY KEY,
    answer TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- jobs -----------------------------------------------------------

    def get_job_status(self, fingerprint: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT status FROM jobs WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return row["status"] if row else None

    def get_status_by_source_url(self, source_url: str) -> Optional[str]:
        """Looks up a previously-seen job by its raw search-result URL. Used
        before full extraction, when only the source_url is known yet — the
        final fingerprint (which also incorporates company/title/external
        id learned during extraction) isn't computable at that point."""
        row = self.conn.execute(
            "SELECT status FROM jobs WHERE source_url = ? ORDER BY updated_at DESC LIMIT 1",
            (source_url,),
        ).fetchone()
        return row["status"] if row else None

    def upsert_job(self, job: JobListing, score: Optional[ScoreBreakdown] = None) -> None:
        self.conn.execute(
            """
            INSERT INTO jobs (
                fingerprint, title, company, location, source_url, application_url,
                external_job_id, domain_policy, status, match_score, score_breakdown_json,
                discovered_via_query, discovered_at, closing_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                status = excluded.status,
                match_score = excluded.match_score,
                score_breakdown_json = excluded.score_breakdown_json,
                application_url = excluded.application_url,
                domain_policy = excluded.domain_policy,
                updated_at = excluded.updated_at
            """,
            (
                job.fingerprint,
                job.title,
                job.company,
                job.location,
                job.source_url,
                job.application_url,
                job.external_job_id,
                job.domain_policy.value if job.domain_policy else None,
                job.status.value,
                score.total if score else None,
                json.dumps(score.as_dict()) if score else None,
                job.discovered_via_query,
                _iso(job.discovered_at),
                _iso(job.closing_date),
                _iso(datetime.utcnow()),
            ),
        )
        self.conn.commit()

    def set_job_status(self, fingerprint: str, status: JobStatus) -> None:
        self.conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE fingerprint = ?",
            (status.value, _iso(datetime.utcnow()), fingerprint),
        )
        self.conn.commit()

    # -- applications -----------------------------------------------------

    def record_application(self, result: ApplicationResult) -> None:
        self.conn.execute(
            """
            INSERT INTO applications (job_fingerprint, applied_at, resume_path, cover_letter_path, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.job.fingerprint,
                _iso(datetime.utcnow()),
                result.resume_path,
                result.cover_letter_path,
                result.status.value,
                result.notes,
            ),
        )
        self.set_job_status(result.job.fingerprint, result.status)
        self.conn.commit()

    def count_applications_since(self, since: datetime) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM applications WHERE applied_at >= ? AND status = ?",
            (_iso(since), JobStatus.APPLIED.value),
        ).fetchone()
        return row["n"]

    def count_applications_today(self) -> int:
        midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.count_applications_since(midnight)

    def count_applications_this_hour(self) -> int:
        return self.count_applications_since(datetime.utcnow() - timedelta(hours=1))

    def count_applications_for_company(self, company: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM applications a
            JOIN jobs j ON j.fingerprint = a.job_fingerprint
            WHERE LOWER(j.company) = LOWER(?) AND a.status = ?
            """,
            (company, JobStatus.APPLIED.value),
        ).fetchone()
        return row["n"]

    # -- pending inputs -----------------------------------------------------

    def add_pending_input(self, pending: PendingInput) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO pending_inputs (job_fingerprint, kind, question, context, created_at, resolved)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (pending.job_id, pending.kind, pending.question, pending.context, _iso(pending.created_at)),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_pending_inputs(self, resolved: bool = False) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pending_inputs WHERE resolved = ? ORDER BY created_at", (int(resolved),)
        ).fetchall()

    def get_pending_input(self, pending_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pending_inputs WHERE id = ?", (pending_id,)
        ).fetchone()

    def resolve_pending_input(self, pending_id: int, answer: str) -> None:
        self.conn.execute(
            "UPDATE pending_inputs SET resolved = 1, answer = ? WHERE id = ?", (answer, pending_id)
        )
        self.conn.commit()

    # -- learned answers -----------------------------------------------------

    def get_learned_answer(self, kind: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT answer FROM learned_answers WHERE kind = ?", (kind,)
        ).fetchone()
        return row["answer"] if row else None

    def set_learned_answer(self, kind: str, answer: str) -> None:
        self.conn.execute(
            """
            INSERT INTO learned_answers (kind, answer, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(kind) DO UPDATE SET answer = excluded.answer, updated_at = excluded.updated_at
            """,
            (kind, answer, _iso(datetime.utcnow())),
        )
        self.conn.commit()

    # -- search query learning -----------------------------------------------------

    def record_query_run(
        self, query: str, jobs_found: int, jobs_matched: int, applications_submitted: int, successful_applications: int
    ) -> None:
        now = _iso(datetime.utcnow())
        self.conn.execute(
            """
            INSERT INTO search_queries (
                query, first_seen_at, last_run_at, runs_count, total_jobs_found,
                total_jobs_matched, total_applications_submitted, total_successful_applications
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(query) DO UPDATE SET
                last_run_at = excluded.last_run_at,
                runs_count = search_queries.runs_count + 1,
                total_jobs_found = search_queries.total_jobs_found + excluded.total_jobs_found,
                total_jobs_matched = search_queries.total_jobs_matched + excluded.total_jobs_matched,
                total_applications_submitted = search_queries.total_applications_submitted + excluded.total_applications_submitted,
                total_successful_applications = search_queries.total_successful_applications + excluded.total_successful_applications
            """,
            (query, now, now, jobs_found, jobs_matched, applications_submitted, successful_applications),
        )
        self.conn.commit()

    def get_query_performance(self) -> dict[str, sqlite3.Row]:
        rows = self.conn.execute("SELECT * FROM search_queries").fetchall()
        return {row["query"]: row for row in rows}

    # -- runs -----------------------------------------------------

    def start_run(self, started_at: datetime) -> int:
        cursor = self.conn.execute(
            "INSERT INTO run_log (started_at) VALUES (?)", (_iso(started_at),)
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, summary: RunSummary) -> None:
        summary_dict = asdict(summary)
        summary_dict["started_at"] = _iso(summary.started_at)
        summary_dict["finished_at"] = _iso(summary.finished_at)
        summary_dict["top_applications"] = [
            {
                "company": r.job.company,
                "title": r.job.title,
                "match_score": r.score.total if r.score else None,
                "status": r.status.value,
            }
            for r in summary.top_applications
        ]
        self.conn.execute(
            "UPDATE run_log SET finished_at = ?, summary_json = ? WHERE id = ?",
            (_iso(summary.finished_at), json.dumps(summary_dict), run_id),
        )
        self.conn.commit()

    def last_run_summary(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT summary_json FROM run_log WHERE summary_json IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return json.loads(row["summary_json"]) if row else None
