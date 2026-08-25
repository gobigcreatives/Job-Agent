"""Tracks which Google queries actually produce relevant, applied-to jobs,
and biases future runs toward them (requirement #11). This only reorders
which of the already-generated queries get spent within the per-run budget
— it never changes how a query is issued or tries to route around a search
engine's own restrictions.

Unseen query variations are treated as worth exploring (score 0.5) rather
than assumed bad, so new role/skill/location combinations still get a fair
try before being judged.
"""
from __future__ import annotations

import sqlite3

from jobagent.tracking.store import Store

_EXPLORATION_SCORE = 0.5


def _yield_score(row: sqlite3.Row | None) -> float:
    if row is None:
        return _EXPLORATION_SCORE
    found = row["total_jobs_found"] or 0
    if found == 0:
        return _EXPLORATION_SCORE
    matched = row["total_jobs_matched"] or 0
    applied = row["total_applications_submitted"] or 0
    return 0.6 * (matched / found) + 0.4 * (applied / found)


def prioritize_queries(queries: list[str], store: Store, max_queries: int) -> list[str]:
    performance = store.get_query_performance()
    ranked = sorted(queries, key=lambda q: _yield_score(performance.get(q)), reverse=True)
    return ranked[:max_queries]
