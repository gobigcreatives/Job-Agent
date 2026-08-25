import pytest
import responses

from jobagent.search.providers import (
    SERPER_SEARCH_ENDPOINT,
    SearchProviderError,
    SerperSearchProvider,
    build_default_provider,
)


@responses.activate
def test_serper_provider_parses_organic_results():
    responses.add(
        responses.POST,
        SERPER_SEARCH_ENDPOINT,
        json={
            "organic": [
                {"title": "Social Media Manager - Acme", "link": "https://acme.example/jobs/1", "snippet": "Great role"},
                {"title": "Content Manager - Beta Co", "link": "https://beta.example/jobs/2", "snippet": "Another role"},
            ]
        },
        status=200,
    )
    provider = SerperSearchProvider(api_key="fake-key")
    results = provider.search("social media manager jobs London", num_results=10)

    assert len(results) == 2
    assert results[0].title == "Social Media Manager - Acme"
    assert results[0].url == "https://acme.example/jobs/1"
    assert results[0].query == "social media manager jobs London"


@responses.activate
def test_serper_provider_sends_api_key_header():
    responses.add(responses.POST, SERPER_SEARCH_ENDPOINT, json={"organic": []}, status=200)
    provider = SerperSearchProvider(api_key="my-secret-key")
    provider.search("test")
    assert responses.calls[0].request.headers["X-API-KEY"] == "my-secret-key"


@responses.activate
def test_serper_provider_raises_on_error_status():
    responses.add(responses.POST, SERPER_SEARCH_ENDPOINT, json={"error": "bad request"}, status=400)
    provider = SerperSearchProvider(api_key="fake-key")
    with pytest.raises(SearchProviderError, match="Serper API error 400"):
        provider.search("test")


def test_serper_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(SearchProviderError, match="SERPER_API_KEY"):
        SerperSearchProvider()


def test_build_default_provider_prefers_serper(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "fake-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "fake-cse")
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    provider = build_default_provider()
    assert isinstance(provider, SerperSearchProvider)


def test_build_default_provider_falls_back_to_google(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "fake-cse")
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    from jobagent.search.providers import GoogleCustomSearchProvider

    provider = build_default_provider()
    assert isinstance(provider, GoogleCustomSearchProvider)


def test_build_default_provider_explicit_override(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "fake-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "fake-cse")
    monkeypatch.setenv("SEARCH_PROVIDER", "google")
    from jobagent.search.providers import GoogleCustomSearchProvider

    provider = build_default_provider()
    assert isinstance(provider, GoogleCustomSearchProvider)


def test_build_default_provider_raises_with_no_credentials(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    with pytest.raises(SearchProviderError, match="No search provider configured"):
        build_default_provider()
