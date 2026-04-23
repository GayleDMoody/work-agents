"""CrewAI-style Task and TaskOutput models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Type

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    RAW = "raw"
    JSON = "json"
    PYDANTIC = "pydantic"


class TaskOutput(BaseModel):
    """Output from a completed task — mirrors CrewAI's TaskOutput."""

    task_id: str
    description: str
    expected_output: str
    raw: str = ""
    summary: str = ""
    json_dict: Optional[dict[str, Any]] = None
    pydantic: Optional[BaseModel] = None
    agent: str = ""
    output_format: OutputFormat = OutputFormat.RAW

    class Config:
        arbitrary_types_allowed = True


class Task(BaseModel):
    """
    CrewAI-style Task — a unit of work assigned to an agent.

    Usage:
        task = Task(
            description="Analyze the ticket requirements",
            expected_output="JSON with acceptance_criteria, edge_cases, risks",
            agent=product_agent,
        )

    Context passing:
        dependent_task = Task(
            description="Write tests based on the code",
            expected_output="pytest test files",
            agent=qa_agent,
            context=[code_task],  # receives code_task's output
        )
    """

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    expected_output: str
    agent: Optional[Any] = None  # BaseAgent instance (Any to avoid circular import)
    context: list["Task"] = Field(default_factory=list)
    async_execution: bool = False
    output_json: Optional[Type] = None
    output_pydantic: Optional[Type[BaseModel]] = None
    output_file: Optional[str] = None
    tools: list[Any] = Field(default_factory=list)

    # Populated after execution
    output: Optional[TaskOutput] = None

    class Config:
        arbitrary_types_allowed = True

    @property
    def completed(self) -> bool:
        return self.output is not None

    def get_context_outputs(self) -> list[TaskOutput]:
        """Get outputs from all context (prerequisite) tasks."""
        return [t.output for t in self.context if t.output is not None]

    def get_context_str(self) -> str:
        """Get a string summary of all context task outputs."""
        outputs = self.get_context_outputs()
        if not outputs:
            return ""
        parts = []
        for o in outputs:
            parts.append(f"--- {o.agent}: {o.description} ---\n{o.raw}\n")
        return "\n".join(parts)
