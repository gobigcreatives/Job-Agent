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
    assert client.model == "gemini-2.5-flash"


def test_client_raises_if_provider_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        LLMClient(provider="gemini")


def test_client_respects_llm_model_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-2.0-flash")
    client = LLMClient()
    assert client.model == "gemini-2.0-flash"
