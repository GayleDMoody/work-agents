"""Code Review Agent — reviews PRs for quality, security, and correctness."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.code_review")


@register_agent("code_review")
class CodeReviewAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "code_review", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="Senior Code Reviewer",
            goal="Review code for correctness, security, performance, and maintainability",
            backstory="You are a senior engineer performing thorough code reviews. You check for security vulnerabilities, performance issues, code quality, and adherence to best practices.",
            capabilities=[AgentCapability.CODE_REVIEW],
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
            f"Review this code for a PR:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON:\n"
            f'{{"decision": "approve|changes_requested", '
            f'"summary": "Overall review summary", '
            f'"comments": [{{"file": "...", "line": 0, "severity": "critical|warning|suggestion", "comment": "..."}}], '
            f'"security_issues": ["..."], '
            f'"performance_concerns": ["..."], '
            f'"test_coverage_assessment": "adequate|insufficient|good"}}'
        )

        try:
            result = await self.call_claude_json(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.system_prompt,
                model=self.model,
                max_tokens=4096,
            )
            meta = result.pop("_meta", {})

            approved = result.get("decision") == "approve"
            critical_issues = [c for c in result.get("comments", []) if c.get("severity") == "critical"]

            return AgentResult(
                agent_id=self.agent_id,
                success=approved or not critical_issues,
                raw=json.dumps(result),
                messages=[
                    f"Review: {result.get('decision', 'unknown')} — {len(result.get('comments', []))} comments",
                    f"Security issues: {len(result.get('security_issues', []))}",
                ],
                metadata=result,
                needs_human_review=bool(critical_issues),
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
        return "decision" in result.metadata

    def can_handle(self, classification: dict[str, Any]) -> float:
        return 0.9  # Code review almost always runs
