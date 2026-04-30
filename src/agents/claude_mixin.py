"""Shared Claude API interaction logic for agents."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import anthropic

from src.observability.logging import get_logger

log = get_logger("claude_mixin")


# ---------------------------------------------------------------------------
# Agent thought-stream emitter
# ---------------------------------------------------------------------------
# A process-wide list of subscribers that get notified every time an agent
# emits a "thought" — i.e. a Claude prompt going out, a Claude response coming
# back, an error, or an inter-agent message. The API layer registers a
# subscriber that converts each event into a WebSocket broadcast so the
# dashboard can render live agent chat panels during a pipeline run.

from typing import Callable, List

_thought_subscribers: List[Callable[[dict], None]] = []


def subscribe_to_thoughts(callback: Callable[[dict], None]) -> Callable[[], None]:
    """Register a callback that gets called on every agent thought event.
    Returns an unsubscribe function. Callbacks must be quick / non-blocking;
    long-running work should be dispatched to a task."""
    _thought_subscribers.append(callback)
    def unsubscribe() -> None:
        try:
            _thought_subscribers.remove(callback)
        except ValueError:
            pass
    return unsubscribe


def _emit_agent_thought(agent_id: str, kind: str, content: str, *, extra: dict | None = None) -> None:
    """kind: 'prompt' | 'response' | 'error' | 'message_sent' | 'message_received'."""
    if not _thought_subscribers:
        return
    payload = {
        "agent_id": agent_id,
        "kind": kind,
        "content": content,
        "timestamp": time.time(),
    }
    if extra:
        payload.update(extra)
    for cb in list(_thought_subscribers):
        try:
            cb(payload)
        except Exception:
            pass


def _summarise_messages(messages: list[dict[str, Any]], system_prompt: str) -> str:
    """Build a short human-readable preview of an outgoing Claude request for
    the live thought stream. Trims long content so the chat panel stays usable."""
    parts: list[str] = []
    if system_prompt:
        # Show only the opening lines of the system prompt — full text is huge
        sp_first = (system_prompt.strip().split("\n", 3)[:2])
        parts.append("[system] " + " / ".join(sp_first)[:160])
    for m in messages[-3:]:  # last 3 messages
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        text = (content or "").strip().replace("\n", " ")
        if len(text) > 600:
            text = text[:600] + "…"
        parts.append(f"[{role}] {text}")
    return "\n".join(parts)


class ClaudeMixin:
    """Mixin providing Claude API interaction methods for agents."""

    _client: anthropic.Anthropic | None = None

    @classmethod
    def get_client(cls, api_key: str | None = None) -> anthropic.Anthropic:
        if cls._client is None:
            cls._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        return cls._client

    @classmethod
    def set_client(cls, client: anthropic.Anthropic) -> None:
        """Set a custom client (useful for testing)."""
        cls._client = client

    async def call_claude(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str = "",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Call Claude API and return the response with token tracking.

        Returns:
            {
                "content": str,  # The text response
                "input_tokens": int,
                "output_tokens": int,
                "duration_seconds": float,
                "model": str,
            }
        """
        client = self.get_client(api_key)
        start = time.time()

        # Emit a thought-stream event for the prompt (if this mixin is on a
        # BaseAgent that has a bus / agent_id). Best-effort; silent on failure.
        agent_id = getattr(self, "agent_id", "") or ""
        if agent_id:
            _emit_agent_thought(agent_id, "prompt", _summarise_messages(messages, system_prompt))

        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else anthropic.NOT_GIVEN,
                messages=messages,
            )

            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            duration = time.time() - start
            result = {
                "content": content,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "duration_seconds": duration,
                "model": model,
            }

            if agent_id:
                _emit_agent_thought(agent_id, "response", content[:1200], extra={
                    "model": model,
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "duration_seconds": round(duration, 2),
                })

            log.debug(
                "claude_call_complete",
                model=model,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                duration=f"{duration:.1f}s",
            )
            return result

        except Exception as e:
            if agent_id:
                _emit_agent_thought(agent_id, "error", str(e)[:300])
            log.error("claude_call_failed", model=model, error=str(e))
            raise

    async def call_claude_json(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str = "",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4096,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Call Claude and parse the response as JSON.

        Returns the parsed JSON dict with _meta field containing token info.
        """
        result = await self.call_claude(
            messages=messages,
            system_prompt=system_prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation.",
            model=model,
            max_tokens=max_tokens,
            api_key=api_key,
        )

        content = result["content"].strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            content = "\n".join(lines)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                parsed = json.loads(content[start_idx:end_idx])
            else:
                raise ValueError(f"Could not parse JSON from response: {content[:200]}")

        parsed["_meta"] = {
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "duration_seconds": result["duration_seconds"],
            "model": result["model"],
        }
        return parsed
