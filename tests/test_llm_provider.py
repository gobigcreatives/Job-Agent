import os

import pytest

from jobagent.generation.llm import LLMClient, LLMError, _autodetect_provider


def test_autodetects_gemini_when_only_gemini_key_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    assert _autodetect_provider() == "gemini"


def test_autodetects_anthropic_when_only_anthropic_key_set(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    assert _autodetect_provider() == "anthropic"


def test_gemini_preferred_when_both_keys_set_and_no_explicit_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert _autodetect_provider() == "gemini"


def test_explicit_provider_overrides_autodetection(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert _autodetect_provider() == "anthropic"


def test_no_keys_set_raises_helpful_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(LLMError, match="aistudio.google.com"):
        _autodetect_provider()


def test_client_uses_gemini_default_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    client = LLMClient()
    assert client.provider == "gemini"
    assert client.model == "gemini-3.6-flash"


def test_client_raises_if_provider_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        LLMClient(provider="gemini")


def test_client_respects_llm_model_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-2.0-flash")
    client = LLMClient()
    assert client.model == "gemini-2.0-flash"


def test_gemini_client_uses_explicit_key_even_when_google_api_key_also_set(monkeypatch):
    # Regression test: this project also uses GOOGLE_API_KEY for Google
    # Custom Search. The google-genai SDK reads that same env var name
    # ahead of an explicitly-passed api_key, so without the env-shielding
    # in _ensure_client() this would silently authenticate Gemini calls
    # with the search key instead of GEMINI_API_KEY.
    monkeypatch.setenv("GOOGLE_API_KEY", "search-key-should-not-be-used-by-gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "the-real-gemini-key")
    client = LLMClient()

    genai_client = client._ensure_client()

    assert genai_client._api_client.api_key == "the-real-gemini-key"
    # the search provider still needs this afterward — must not be wiped
    assert os.environ["GOOGLE_API_KEY"] == "search-key-should-not-be-used-by-gemini"
