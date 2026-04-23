"""DevOps Agent — handles CI/CD, deployment configs, infrastructure."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.devops")


@register_agent("devops")
class DevOpsAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "devops", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="DevOps Engineer",
            goal="Handle CI/CD pipelines, deployment configs, and infrastructure changes",
            backstory="You are an experienced DevOps engineer who manages CI/CD pipelines, Docker configs, and deployment infrastructure. You ensure smooth deployments.",
            capabilities=[AgentCapability.DEVOPS],
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
            f"Review infrastructure needs for:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON:\n"
            f'{{"config_files": [{{"path": "...", "content": "...", "action": "create|modify"}}], '
            f'"env_vars_needed": [{{"name": "...", "description": "...", "required": true}}], '
            f'"deployment_notes": "...", '
            f'"ci_changes_needed": true/false}}'
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
                messages=[f"Generated {len(result.get('config_files', []))} config files"],
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
        return result.success and bool(result.raw)

    def can_handle(self, classification: dict[str, Any]) -> float:
        if classification.get("ticket_type") == "infra":
            return 1.0
        if "devops" in classification.get("required_agents", []):
            return 0.9
        return 0.1
