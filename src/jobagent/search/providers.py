"""Search provider abstraction. The only implementation wired to a real
network call is GoogleCustomSearchProvider, which uses the Google
Programmable Search Engine (Custom Search JSON API) — the officially
supported way to run Google searches programmatically without scraping
google.com search result pages (scraping google.com directly breaks its
terms of service and is unreliable; this project intentionally avoids it).

Set GOOGLE_API_KEY and GOOGLE_CSE_ID (see .env.example) to enable it.
"""
from __future__ import annotations

import abc
import logging
import os
import time

import requests

from jobagent.models import SearchResult

logger = logging.getLogger(__name__)

GOOGLE_CUSTOM_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class SearchProviderError(RuntimeError):
    pass


class SearchProvider(abc.ABC):
    @abc.abstractmethod
    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        ...


class GoogleCustomSearchProvider(SearchProvider):
    """Wraps the Google Custom Search JSON API. Configure a Programmable
    Search Engine at https://programmablesearchengine.google.com/ set to
    "search the entire web" (not restricted to specific sites) so it can
    actually discover arbitrary company career pages."""

    def __init__(self, api_key: str | None = None, cse_id: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.cse_id = cse_id or os.environ.get("GOOGLE_CSE_ID")
        if not self.api_key or not self.cse_id:
            raise SearchProviderError(
                "GOOGLE_API_KEY and GOOGLE_CSE_ID must be set (see .env.example) to use "
                "GoogleCustomSearchProvider."
            )
        self.session = session or requests.Session()

    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        results: list[SearchResult] = []
        # The API returns at most 10 results per call and is paginated via
        # `start`; loop until we have enough or the API says there's nothing
        # left.
        start = 1
        while len(results) < num_results:
            page_size = min(10, num_results - len(results))
            params = {
                "key": self.api_key,
                "cx": self.cse_id,
                "q": query,
                "num": page_size,
                "start": start,
            }
            response = self.session.get(GOOGLE_CUSTOM_SEARCH_ENDPOINT, params=params, timeout=15)
            if response.status_code == 429:
                raise SearchProviderError("Google Custom Search API rate limit hit (HTTP 429)")
            if not response.ok:
                raise SearchProviderError(
                    f"Google Custom Search API error {response.status_code}: {response.text[:300]}"
                )
            payload = response.json()
            items = payload.get("items", [])
            for item in items:
                results.append(
                    SearchResult(
                        query=query,
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                    )
                )
            if not items or len(items) < page_size:
                break
            start += page_size
        return results[:num_results]


class StaticSearchProvider(SearchProvider):
    """Returns pre-seeded results. Used for tests and for dry-running the
    pipeline without API credentials — never wired in by default."""

    def __init__(self, canned_results: dict[str, list[SearchResult]] | None = None):
        self.canned_results = canned_results or {}

    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        return self.canned_results.get(query, [])[:num_results]


class RateLimitedProvider(SearchProvider):
    """Wraps another provider to enforce a minimum delay between outbound
    requests (requirement #6: "do not create excessive search traffic")."""

    def __init__(self, inner: SearchProvider, min_delay_seconds: float = 2.0):
        self.inner = inner
        self.min_delay_seconds = min_delay_seconds
        self._last_call: float | None = None

    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        if self._last_call is not None:
            elapsed = time.monotonic() - self._last_call
            wait = self.min_delay_seconds - elapsed
            if wait > 0:
                time.sleep(wait)
        self._last_call = time.monotonic()
        return self.inner.search(query, num_results)
