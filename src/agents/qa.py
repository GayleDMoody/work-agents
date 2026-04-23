"""QA Agent — writes test plans and automated tests."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.qa")


@register_agent("qa")
class QAAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "qa", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="QA Engineer",
            goal="Write comprehensive test plans and automated tests to ensure code quality",
            backstory="You are an experienced QA engineer who writes thorough test plans and automated tests. You think about edge cases, error conditions, and integration points.",
            capabilities=[AgentCapability.TESTING],
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
            f"Write tests for the following task:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON:\n"
            f'{{"test_plan": "Overall test strategy", '
            f'"test_files": [{{"path": "tests/...", "content": "# full test file", "test_count": 5}}], '
            f'"edge_cases_covered": ["..."], '
            f'"coverage_estimate": "80%", '
            f'"risks_not_covered": ["..."]}}'
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
                messages=[f"Generated {len(result.get('test_files', []))} test files"],
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
        test_files = result.metadata.get("test_files", [])
        return len(test_files) > 0

    def can_handle(self, classification: dict[str, Any]) -> float:
        return 0.9  # QA almost always runs
