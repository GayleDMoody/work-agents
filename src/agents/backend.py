"""Backend Agent — writes Python backend code."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.backend")


@register_agent("backend")
class BackendAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "backend", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="Backend Developer",
            goal="Write production-quality Python backend code with proper error handling",
            backstory="You are a senior backend developer specializing in Python. You write clean, well-tested code with proper error handling, logging, and type hints. You follow existing patterns in the codebase.",
            capabilities=[AgentCapability.BACKEND_CODE],
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
            f"Write backend code for:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON with files to create/modify:\n"
            f'{{"files": [{{"path": "src/...", "content": "# full file content", "action": "create|modify"}}], '
            f'"summary": "What was implemented", '
            f'"dependencies_added": [], '
            f'"env_vars_needed": []}}'
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
                messages=[f"Generated {len(result.get('files', []))} backend files"],
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
        if "backend" in scope:
            return 1.0
        return 0.0
