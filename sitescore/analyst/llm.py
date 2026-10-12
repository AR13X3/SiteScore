"""A minimal streaming client for OpenRouter's OpenAI-compatible chat API, with tool calls.

Only what the analyst needs: stream text deltas as they arrive and collect tool calls,
whose arguments arrive in fragments. Kept behind the `ChatModel` protocol so tests can
script the model's turns without the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(RuntimeError):
    """The model provider refused or failed the request."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""

    def args(self) -> dict[str, Any]:
        """Parsed arguments; a model that sends broken JSON gets an empty dict."""
        try:
            value = json.loads(self.arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


@dataclass
class Turn:
    """One model turn: its text (streamed separately) and any tool calls it made."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


class ChatModel(Protocol):
    name: str

    def stream(self, messages: list[dict], tools: list[dict]) -> Iterator[str | Turn]:
        """Yield text deltas (str) as they arrive, then the finished Turn last."""
        ...


class OpenRouterModel:
    def __init__(self, api_key: str, model: str, *, timeout: float = 120.0,
                 max_tokens: int = 4000) -> None:
        self.api_key = api_key
        self.name = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def stream(self, messages: list[dict], tools: list[dict]) -> Iterator[str | Turn]:
        body = {
            "model": self.name,
            "messages": messages,
            "tools": tools,
            "stream": True,
            "max_tokens": self.max_tokens,
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            # OpenRouter attribution headers (optional, shown on openrouter.ai rankings).
            "HTTP-Referer": "https://github.com/AR13X3/SiteScore",
            "X-Title": "SiteScore",
        }
        turn = Turn()
        calls: dict[int, ToolCall] = {}
        timeout = httpx.Timeout(self.timeout, connect=15.0)
        try:
            with httpx.stream("POST", OPENROUTER_URL, json=body, headers=headers,
                              timeout=timeout) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise LLMError(_error_message(resp))
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise LLMError(str(chunk["error"].get("message", chunk["error"])))
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            turn.text += delta["content"]
                            yield delta["content"]
                        for tc in delta.get("tool_calls") or []:
                            call = calls.setdefault(tc.get("index", 0), ToolCall(id="", name=""))
                            call.id = tc.get("id") or call.id
                            fn = tc.get("function") or {}
                            call.name = fn.get("name") or call.name
                            call.arguments += fn.get("arguments") or ""
                        if choice.get("finish_reason"):
                            turn.finish_reason = choice["finish_reason"]
        except httpx.HTTPError as exc:
            raise LLMError(f"Couldn't reach OpenRouter: {exc}") from exc
        turn.tool_calls = [c for _, c in sorted(calls.items()) if c.name]
        for i, c in enumerate(turn.tool_calls):
            c.id = c.id or f"call_{i}"
        yield turn


def _error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except (json.JSONDecodeError, AttributeError):
        msg = resp.text[:300]
    hint = {401: " Check OPENROUTER_API_KEY in .env.",
            402: " Your OpenRouter account is out of credit.",
            404: " Check OPENROUTER_MODEL in .env: it must be a model OpenRouter lists.",
            429: " OpenRouter is rate-limiting: try again in a moment."}.get(resp.status_code, "")
    return f"OpenRouter {resp.status_code}: {msg or resp.reason_phrase}.{hint}"
