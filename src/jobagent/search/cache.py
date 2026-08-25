"""SQLite-backed cache so identical queries aren't re-issued to Google
within the configured TTL (requirement #6: reasonable rate limits and
caching). Wrapping a provider in CachingSearchProvider makes caching
transparent to callers — they just call `.search()` as normal.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from jobagent.models import SearchResult
from jobagent.search.providers import SearchProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_cache (
    query TEXT PRIMARY KEY,
    results_json TEXT NOT NULL,
    cached_at REAL NOT NULL
);
"""


class SearchCache:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def get(self, query: str, ttl_hours: float) -> list[SearchResult] | None:
        row = self.conn.execute(
            "SELECT results_json, cached_at FROM search_cache WHERE query = ?", (query,)
        ).fetchone()
        if row is None:
            return None
        results_json, cached_at = row
        if time.time() - cached_at > ttl_hours * 3600:
            return None
        raw = json.loads(results_json)
        return [SearchResult(**item) for item in raw]

    def set(self, query: str, results: list[SearchResult]) -> None:
        payload = json.dumps([r.__dict__ for r in results])
        self.conn.execute(
            "INSERT INTO search_cache (query, results_json, cached_at) VALUES (?, ?, ?) "
            "ON CONFLICT(query) DO UPDATE SET results_json = excluded.results_json, cached_at = excluded.cached_at",
            (query, payload, time.time()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class CachingSearchProvider(SearchProvider):
    def __init__(self, inner: SearchProvider, cache: SearchCache, ttl_hours: float):
        self.inner = inner
        self.cache = cache
        self.ttl_hours = ttl_hours
        self.last_query_was_cache_hit = False

    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        cached = self.cache.get(query, self.ttl_hours)
        if cached is not None:
            self.last_query_was_cache_hit = True
            return cached[:num_results]
        self.last_query_was_cache_hit = False
        results = self.inner.search(query, num_results)
        self.cache.set(query, results)
        return results
