"""OpenAI client factory and safe-call helpers.

Centralizes client creation so the same module can be patched in tests
(monkeypatch `app.core.openai_client.get_client`) and reused for both
text-only and vision-capable calls.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from app.core.config import get_settings

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    """Return a process-wide AsyncOpenAI client, lazily created."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-missing",
            timeout=settings.openai_timeout_seconds,
        )
    return _client


def reset_client() -> None:
    """Drop the cached client (useful in tests after monkeypatching config)."""
    global _client
    _client = None


def is_configured() -> bool:
    return bool(get_settings().openai_api_key)


async def chat_json(
    *,
    model: str,
    messages: list[Dict[str, Any]],
    max_tokens: int = 600,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Call OpenAI chat completions enforcing JSON output.

    Uses `response_format={"type":"json_object"}` so the model is
    guaranteed to return parseable JSON.
    """
    client = get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "").strip()
    import json
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned non-JSON content: {content[:200]}") from exc