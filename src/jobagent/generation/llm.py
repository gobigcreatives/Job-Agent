"""Thin wrapper around the Anthropic API, used for CV tailoring, cover
letter generation, and ambiguous-application-question triage. Isolated here
so those callers don't each need to know how to construct a client.
"""
from __future__ import annotations

import os

DEFAULT_MODEL = "claude-sonnet-5"


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY must be set (see .env.example) to use CV tailoring, "
                "cover letter generation, or question triage."
            )
        self.model = model
        self._client = None  # lazily constructed — importing anthropic is not free

    def _ensure_client(self):
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> str:
        client = self._ensure_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
