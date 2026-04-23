"""Ticket classification model."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TicketClassification(BaseModel):
    """Result of classifying a Jira ticket."""

    ticket_type: str  # "feature", "bug", "refactor", "infra", "docs"
    scope: list[str] = Field(default_factory=list)  # ["frontend"], ["backend"], ["frontend", "backend"]
    complexity: str = "M"  # "S", "M", "L", "XL"
    risk_level: str = "low"  # "low", "medium", "high"
    required_agents: list[str] = Field(default_factory=list)
    optional_agents: list[str] = Field(default_factory=list)
    rationale: str = ""
    estimated_files: int = 1
    needs_human_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
