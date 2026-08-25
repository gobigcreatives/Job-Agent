"""Thin wrapper around whichever LLM backend is configured, used for CV
tailoring, cover letter generation, and ambiguous-application-question
triage. Two backends are supported so a paid Anthropic key is never
required to run this project:

- Google Gemini (via Google AI Studio, https://aistudio.google.com/apikey)
  — genuinely free tier, no credit card, generous daily quota for a
  personal job-search volume of traffic. This is the recommended default.
- Anthropic (Claude) — used if ANTHROPIC_API_KEY is set, or if
  LLM_PROVIDER=anthropic is set explicitly.

Set GEMINI_API_KEY (or ANTHROPIC_API_KEY) in .env; whichever is present is
auto-detected. Set LLM_PROVIDER explicitly to force one when both are set.
"""
from __future__ import annotations

import os

_DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "anthropic": "claude-sonnet-5",
}


class LLMError(RuntimeError):
    pass


def _autodetect_provider() -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit:
        if explicit not in _DEFAULT_MODELS:
            raise LLMError(f"LLM_PROVIDER='{explicit}' is not supported (use 'gemini' or 'anthropic')")
        return explicit
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise LLMError(
        "No LLM configured. Set GEMINI_API_KEY (free — get one at "
        "https://aistudio.google.com/apikey) or ANTHROPIC_API_KEY in .env. "
        "See .env.example."
    )


class LLMClient:
    def __init__(self, provider: str | None = None, api_key: str | None = None, model: str | None = None):
        self.provider = provider or _autodetect_provider()
        if self.provider not in _DEFAULT_MODELS:
            raise LLMError(f"Unsupported LLM provider '{self.provider}' (use 'gemini' or 'anthropic')")

        env_key_name = "GEMINI_API_KEY" if self.provider == "gemini" else "ANTHROPIC_API_KEY"
        self.api_key = api_key or os.environ.get(env_key_name)
        if not self.api_key:
            raise LLMError(f"{env_key_name} must be set (see .env.example) to use the '{self.provider}' provider.")

        self.model = model or os.environ.get("LLM_MODEL") or _DEFAULT_MODELS[self.provider]
        self._client = None  # lazily constructed — importing the SDK is not free

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if self.provider == "gemini":
            from google import genai

            # The google-genai SDK checks its own GOOGLE_API_KEY/GEMINI_API_KEY
            # env vars ahead of an explicitly-passed api_key. GOOGLE_API_KEY is
            # also this project's Google Custom Search key, so if both are set
            # in the environment the SDK would silently authenticate Gemini
            # calls with the wrong (search) key. Shield the constructor call
            # from that env var so our explicit api_key always wins.
            previous = os.environ.pop("GOOGLE_API_KEY", None)
            try:
                self._client = genai.Client(api_key=self.api_key)
            finally:
                if previous is not None:
                    os.environ["GOOGLE_API_KEY"] = previous
        else:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> str:
        client = self._ensure_client()
        if self.provider == "gemini":
            from google.genai import types

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
            )
            return (response.text or "").strip()

        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
