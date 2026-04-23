"""Shared context and ticket models that flow through the pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PipelinePhase(str, Enum):
    INTAKE = "intake"
    CLASSIFICATION = "classification"
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    EXECUTION = "execution"
    TESTING = "testing"
    REVIEW = "review"
    DEPLOYMENT = "deployment"
    COMPLETE = "complete"
    FAILED = "failed"


class PhaseTransition(BaseModel):
    from_phase: PipelinePhase
    to_phase: PipelinePhase
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""


class TicketContext(BaseModel):
    """Parsed Jira ticket data."""

    key: str
    summary: str
    description: str = ""
    issue_type: str = "story"
    priority: str = "medium"
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    linked_issues: list[str] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    reporter: str = ""
    assignee: Optional[str] = None
    story_points: Optional[int] = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class FeedbackEntry(BaseModel):
    """Feedback from one agent to another."""

    from_agent: str
    to_agent: str
    feedback_type: str  # "test_failure", "review_comment", "clarification"
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cycle: int = 0


class AgentResultRecord(BaseModel):
    """Record of an agent's execution result."""

    agent_id: str
    phase: PipelinePhase
    success: bool
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SharedContext(BaseModel):
    """The accumulating state object that flows through the pipeline."""

    # Identity
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    ticket: TicketContext

    # Classification (set by router)
    classification: Optional[dict[str, Any]] = None

    # Planning (set by PM agent)
    execution_plan: Optional[dict[str, Any]] = None

    # Architecture (set by architect agent)
    architecture: Optional[dict[str, Any]] = None

    # Agent outputs
    agent_results: list[AgentResultRecord] = Field(default_factory=list)

    # Artifacts (files, docs, test results)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)

    # Feedback log
    feedback_log: list[FeedbackEntry] = Field(default_factory=list)

    # Pipeline state
    current_phase: PipelinePhase = PipelinePhase.INTAKE
    phase_history: list[PhaseTransition] = Field(default_factory=list)

    # Human approvals
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    pending_approval: Optional[dict[str, Any]] = None

    # Git state
    branch_name: Optional[str] = None
    pr_number: Optional[int] = None
    commits: list[str] = Field(default_factory=list)

    # Per-agent conversation history
    agent_conversations: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)

    # --- Mutation helpers ---

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        if "id" not in artifact:
            artifact["id"] = str(uuid.uuid4())[:8]
        if "created_at" not in artifact:
            artifact["created_at"] = datetime.now(timezone.utc).isoformat()
        self.artifacts.append(artifact)

    def add_agent_result(self, result: AgentResultRecord) -> None:
        self.agent_results.append(result)

    def add_feedback(self, from_agent: str, to_agent: str, feedback: dict[str, Any], cycle: int = 0) -> None:
        entry = FeedbackEntry(
            from_agent=from_agent,
            to_agent=to_agent,
            feedback_type=feedback.get("type", "general"),
            details=feedback,
            cycle=cycle,
        )
        self.feedback_log.append(entry)

    def get_artifacts_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        return [a for a in self.artifacts if a.get("agent_id") == agent_id]

    def get_artifacts_by_type(self, artifact_type: str) -> list[dict[str, Any]]:
        return [a for a in self.artifacts if a.get("artifact_type") == artifact_type]

    def transition_to(self, phase: PipelinePhase, reason: str = "") -> None:
        transition = PhaseTransition(
            from_phase=self.current_phase,
            to_phase=phase,
            reason=reason,
        )
        self.phase_history.append(transition)
        self.current_phase = phase
