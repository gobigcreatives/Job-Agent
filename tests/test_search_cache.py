from jobagent.models import SearchResult
from jobagent.search.cache import CachingSearchProvider, SearchCache
from jobagent.search.providers import SearchProvider


class _CountingProvider(SearchProvider):
    def __init__(self):
        self.calls = 0

    def search(self, query, num_results=10):
        self.calls += 1
        return [SearchResult(query=query, title="A role", url=f"https://x.com/{self.calls}", snippet="...")]


def test_second_identical_query_within_ttl_is_a_cache_hit(tmp_path):
    cache = SearchCache(tmp_path / "cache.db")
    inner = _CountingProvider()
    provider = CachingSearchProvider(inner, cache, ttl_hours=1)

    first = provider.search("social media manager London")
    second = provider.search("social media manager London")

    assert inner.calls == 1
    assert first == second


def test_expired_cache_entry_is_refetched(tmp_path):
    cache = SearchCache(tmp_path / "cache.db")
    inner = _CountingProvider()
    provider = CachingSearchProvider(inner, cache, ttl_hours=0)

    provider.search("q")
    provider.search("q")

    assert inner.calls == 2


def test_different_queries_are_not_conflated(tmp_path):
    cache = SearchCache(tmp_path / "cache.db")
    inner = _CountingProvider()
    provider = CachingSearchProvider(inner, cache, ttl_hours=1)

    provider.search("query one")
    provider.search("query two")

    assert inner.calls == 2
