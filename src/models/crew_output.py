"""CrewAI-style CrewOutput — result of a Crew.kickoff() call."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from src.models.task import TaskOutput


class TokenUsage(BaseModel):
    """Token usage across all agents in a crew run."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    by_agent: dict[str, dict[str, int]] = Field(default_factory=dict)


class CrewOutput(BaseModel):
    """
    Result of Crew.kickoff() — mirrors CrewAI's CrewOutput.

    Attributes:
        raw: The final task's raw string output
        pydantic: Structured output (if final task has output_pydantic)
        json_dict: JSON output (if final task has output_json)
        tasks_output: All individual TaskOutput objects
        token_usage: Token consumption metrics
    """

    raw: str = ""
    pydantic: Optional[Any] = None
    json_dict: Optional[dict[str, Any]] = None
    tasks_output: list[TaskOutput] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)

    # Extension fields (not in CrewAI but useful for our pipeline)
    success: bool = True
    duration_seconds: float = 0.0
    run_id: str = ""
    agent_messages: list[dict[str, Any]] = Field(default_factory=list)  # inter-agent chat log

    class Config:
        arbitrary_types_allowed = True
