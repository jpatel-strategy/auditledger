"""Thin wrapper around the Anthropic API, with a safe offline default.

Two design decisions worth explaining to a reviewer:

1. The LLM is optional. When no API key is present (a fresh clone, CI, a demo),
   the pipeline falls back to deterministic logic so the whole system still runs
   and the verification gate is free and reproducible. The AI adds natural
   language and extraction convenience — it is never load-bearing for catching
   errors; the deterministic matcher is.

2. We read the key only from a git-ignored .env / environment. No secret ever
   lives in the repo.
"""

from __future__ import annotations

import os

from .. import config


def is_llm_available() -> bool:
    """True only if we have both the SDK and a key — otherwise we go offline."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


class LLMClient:
    """Minimal Anthropic client used for extraction and reasoning prose."""

    def __init__(self, model: str = config.MODEL):
        import anthropic  # imported lazily so the package works without the SDK

        self.model = model
        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        """Return the plain-text content of a single-turn completion."""
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if block.type == "text")


def get_client() -> LLMClient | None:
    """Factory: a live client when possible, otherwise ``None`` (offline mode)."""
    return LLMClient() if is_llm_available() else None


def model_version() -> str:
    """The model identifier stamped into the audit log for provenance."""
    return config.MODEL if is_llm_available() else "deterministic-fallback-v1"
