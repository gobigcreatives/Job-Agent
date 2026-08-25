import pytest

from jobagent.learning.query_performance import prioritize_queries
from jobagent.tracking.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


def test_high_yield_query_ranked_above_low_yield(store):
    store.record_query_run("good query", jobs_found=10, jobs_matched=8, applications_submitted=3, successful_applications=3)
    store.record_query_run("bad query", jobs_found=10, jobs_matched=0, applications_submitted=0, successful_applications=0)

    ranked = prioritize_queries(["bad query", "good query"], store, max_queries=10)
    assert ranked[0] == "good query"


def test_unseen_queries_are_not_penalised_to_the_bottom(store):
    store.record_query_run("bad query", jobs_found=10, jobs_matched=0, applications_submitted=0, successful_applications=0)
    ranked = prioritize_queries(["bad query", "new query"], store, max_queries=10)
    assert ranked[0] == "new query"


def test_respects_max_queries_limit(store):
    queries = [f"query {i}" for i in range(30)]
    ranked = prioritize_queries(queries, store, max_queries=5)
    assert len(ranked) == 5


def test_ties_preserve_original_order(store):
    ranked = prioritize_queries(["a", "b", "c"], store, max_queries=10)
    assert ranked == ["a", "b", "c"]
