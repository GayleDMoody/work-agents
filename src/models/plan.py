"""Execution plan models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """A single step in an execution plan."""

    step_id: str
    agent_id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    is_parallel: bool = False
    approval_required: bool = False
    estimated_tokens: int = 0


class ExecutionPlan(BaseModel):
    """Ordered plan of agent invocations."""

    steps: list[PlanStep] = Field(default_factory=list)
    total_estimated_tokens: int = 0
    critical_path: list[str] = Field(default_factory=list)

    def get_next_steps(self, completed: set[str]) -> list[PlanStep]:
        """Get steps whose dependencies are all completed."""
        ready = []
        for step in self.steps:
            if step.step_id in completed:
                continue
            if all(dep in completed for dep in step.depends_on):
                ready.append(step)
        return ready
