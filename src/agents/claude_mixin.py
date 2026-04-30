"""Shared Claude API interaction logic for agents."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import anthropic

from src.observability.logging import get_logger

log = get_logger("claude_mixin")


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

            log.debug(
                "claude_call_complete",
                model=model,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                duration=f"{duration:.1f}s",
            )
            return result

        except Exception as e:
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
