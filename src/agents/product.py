"""Product Agent — analyzes requirements and creates acceptance criteria."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.product")


@register_agent("product")
class ProductAgent(BaseAgent, ClaudeMixin):
    def __init__(self, agent_id: str = "product", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="Product Analyst",
            goal="Analyze requirements, identify gaps, and create clear acceptance criteria",
            backstory="You are an experienced product analyst who ensures every ticket is well-defined before development begins. You identify ambiguities, missing edge cases, and unclear requirements.",
            capabilities=[AgentCapability.REQUIREMENTS_ANALYSIS],
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
            f"Analyze this ticket and produce structured output:\n\n"
            f"**Task**: {task.description}\n\n"
        )
        if context:
            prompt += f"**Context**:\n{context}\n\n"
        if analysis.get("expected_output"):
            prompt += f"**Expected output**: {analysis['expected_output']}\n\n"

        prompt += (
            f"Provide JSON with:\n"
            f'{{"acceptance_criteria": ["AC1", "AC2", ...], '
            f'"clarification_questions": ["Q1", ...], '
            f'"user_stories": ["As a user, I want..."], '
            f'"edge_cases": ["What if..."], '
            f'"risks": ["Risk description"], '
            f'"is_well_defined": true/false}}'
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
                messages=[f"Analyzed task: {len(result.get('acceptance_criteria', []))} acceptance criteria"],
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
        # Must have at least some acceptance criteria
        ac = result.metadata.get("acceptance_criteria", [])
        return len(ac) > 0

    def can_handle(self, classification: dict[str, Any]) -> float:
        return 1.0  # Product agent always runs
