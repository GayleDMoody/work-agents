"""Frontend Agent — writes React/TypeScript code."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.frontend")


@register_agent("frontend")
class FrontendAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "frontend", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="Frontend Developer",
            goal="Write production-quality React/TypeScript frontend code",
            backstory="You are a senior frontend developer specializing in React and TypeScript. You write clean, accessible, well-typed components that follow existing codebase patterns.",
            capabilities=[AgentCapability.FRONTEND_CODE],
            **{k: v for k, v in kwargs.items() if k in ("model", "max_retries", "system_prompt_file", "llm", "verbose")},
        )

    async def analyze(self, task: Any, context: str) -> dict[str, Any]:
        return {
            "description": task.description,
            "expected_output": getattr(task, "expected_output", ""),
            "has_context": bool(context),
        }

    async def execute(self, task: Any, context: str, analysis: dict[str, Any]) -> AgentResult:
        prompt = (
            f"Write frontend code for:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON with files to create/modify:\n"
            f'{{"files": [{{"path": "src/components/...", "content": "// full file content", "action": "create|modify"}}], '
            f'"summary": "What was implemented", '
            f'"dependencies_added": []}}'
        )

        try:
            result = await self.call_claude_json(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.system_prompt,
                model=self.model,
                max_tokens=8192,
            )
            meta = result.pop("_meta", {})

            return AgentResult(
                agent_id=self.agent_id,
                success=True,
                raw=json.dumps(result),
                messages=[f"Generated {len(result.get('files', []))} frontend files"],
                metadata=result,
                input_tokens=meta.get("input_tokens", 0),
                output_tokens=meta.get("output_tokens", 0),
            )
        except Exception as e:
            return AgentResult(
                agent_id=self.agent_id,
                success=False,
                errors=[str(e)],
                retry_recommended=True,
            )

    async def validate(self, task: Any, result: AgentResult) -> bool:
        if not result.success:
            return False
        files = result.metadata.get("files", [])
        return len(files) > 0

    def can_handle(self, classification: dict[str, Any]) -> float:
        scope = classification.get("scope", [])
        if "frontend" in scope:
            return 1.0
        return 0.0
