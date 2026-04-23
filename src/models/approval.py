"""Approval gate models for human-in-the-loop."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApprovalGate(str, Enum):
    TICKET_CLARIFICATION = "ticket_clarification"
    ARCHITECTURE = "architecture"
    PRE_MERGE = "pre_merge"
    DEPLOYMENT = "deployment"


class ApprovalRequest(BaseModel):
    """Request for human approval at a gate."""

    id: str
    gate: ApprovalGate
    run_id: str
    ticket_key: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_hours: int = 24


class ApprovalResult(BaseModel):
    """Result of a human approval decision."""

    request_id: str
    approved: bool
    reviewer: str = ""
    feedback: str = ""
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
