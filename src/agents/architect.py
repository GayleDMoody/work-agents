"""Architect Agent — designs technical solutions and defines interfaces."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.architect")


@register_agent("architect")
class ArchitectAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "architect", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="Software Architect",
            goal="Design technical solutions, define interfaces, and establish patterns",
            backstory="You are a senior software architect who designs scalable, maintainable solutions. You consider existing codebase patterns, define clear interfaces, and create file change manifests.",
            capabilities=[AgentCapability.ARCHITECTURE],
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
            f"Design the technical approach for:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON:\n"
            f'{{"approach": "High-level approach description", '
            f'"files_to_create": [{{"path": "src/...", "purpose": "..."}}], '
            f'"files_to_modify": [{{"path": "src/...", "changes": "..."}}], '
            f'"interfaces": [{{"name": "...", "definition": "..."}}], '
            f'"patterns": ["Pattern to follow"], '
            f'"dependencies": ["New dependencies if any"], '
            f'"risks": ["Technical risks"], '
            f'"notes": "Additional notes"}}'
        )

        try:
            result = await self.call_claude_json(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.system_prompt,
                model=self.model,
            )
            meta = result.pop("_meta", {})

            return AgentResult(
                agent_id=self.agent_id,
                success=True,
                raw=json.dumps(result),
                messages=[f"Architecture designed: {len(result.get('files_to_create', []))} new files, {len(result.get('files_to_modify', []))} modified"],
                metadata=result,
                needs_human_review=True,
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
        return bool(result.metadata.get("approach"))

    def can_handle(self, classification: dict[str, Any]) -> float:
        complexity = classification.get("complexity", "S")
        ticket_type = classification.get("ticket_type", "")
        if complexity in ("L", "XL"):
            return 0.9
        if ticket_type in ("feature", "refactor"):
            return 0.7
        if classification.get("estimated_files", 0) > 3:
            return 0.8
        return 0.2
