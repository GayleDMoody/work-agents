"""
BaseAgent — CrewAI-compatible agent with our three-phase internals.

Public API matches CrewAI:
    Agent(role, goal, backstory, tools=[], llm=None, allow_delegation=False)
    agent.execute_task(task, context_str) -> TaskOutput

Internally keeps analyze/execute/validate for quality control.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.observability.logging import get_logger

log = get_logger("agent")


class AgentCapability(str, Enum):
    REQUIREMENTS_ANALYSIS = "requirements_analysis"
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    FRONTEND_CODE = "frontend_code"
    BACKEND_CODE = "backend_code"
    TESTING = "testing"
    DEVOPS = "devops"
    CODE_REVIEW = "code_review"


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class AgentResult:
    """Internal result from agent execution."""

    agent_id: str
    success: bool
    raw: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    retry_recommended: bool = False
    needs_human_review: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0


class BaseAgent(ABC):
    """
    CrewAI-compatible agent base class.

    Constructor matches CrewAI's Agent:
        Agent(role, goal, backstory, tools=[], llm=None, ...)

    Execution via execute_task(task, context_str) → TaskOutput
    Internally uses three-phase protocol (analyze/execute/validate).
    """

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        agent_id: str = "",
        tools: list[Any] | None = None,
        llm: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        allow_delegation: bool = False,
        max_iter: int = 20,
        max_retries: int = 2,
        verbose: bool = False,
        system_prompt_file: str | None = None,
        capabilities: list[AgentCapability] | None = None,
        **kwargs,  # Accept extra config keys gracefully
    ):
        self.agent_id = agent_id or role.lower().replace(" ", "_")
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.tools = tools or []
        self.model = llm or model
        self.allow_delegation = allow_delegation
        self.max_iter = max_iter
        self.max_retries = max_retries
        self.verbose = verbose
        self.capabilities = capabilities or []
        self.status = AgentStatus.IDLE
        self._system_prompt: str | None = None
        self._bus: Any = None  # AgentBus instance, set by Crew
        self._msg_read_index: int = 0  # tracks inbox read position

        if system_prompt_file:
            prompt_path = Path(system_prompt_file)
            if prompt_path.exists():
                self._system_prompt = prompt_path.read_text()

    # Short reminder appended to every agent's system prompt so agents know
    # the message bus exists and don't guess when requirements are unclear.
    # (PM overrides system_prompt entirely and provides its own richer guidance.)
    TEAM_COMMUNICATION_TIPS: str = (
        "\n\n## Working with the team\n"
        "You are part of a multi-agent team. If you have a teammate's messages at "
        "the top of your context (under 'Team Messages'), read them — they may "
        "answer your questions or flag issues.\n"
        "If a requirement is ambiguous, DO NOT guess. Flag the ambiguity clearly "
        "in your output (e.g., in a `questions` or `clarifications_needed` field) "
        "and note which teammate should answer (usually `product` for requirements, "
        "`architect` for design, `pm` for scope/priority). The orchestrator will "
        "route these questions across the team."
    )

    @property
    def system_prompt(self) -> str:
        base = self._system_prompt or (
            f"You are a {self.role}.\n\n"
            f"## Goal\n{self.goal}\n\n"
            f"## Backstory\n{self.backstory}\n\n"
            "Always respond with valid JSON when asked for structured output."
        )
        return base + self.TEAM_COMMUNICATION_TIPS

    # ------------------------------------------------------------------
    # CrewAI-compatible public API
    # ------------------------------------------------------------------

    async def execute_task(self, task: Any, context: str = "") -> Any:
        """
        Execute a Task and return a TaskOutput.
        This is the CrewAI-compatible entry point.
        """
        from src.models.task import Task, TaskOutput, OutputFormat

        start = time.time()
        self.status = AgentStatus.BUSY
        log.info("agent_executing_task", agent_id=self.agent_id, task_id=task.task_id)

        try:
            # Build full context from task dependencies + any extra context
            full_context = task.get_context_str()
            if context:
                full_context = context + "\n\n" + full_context

            # Prepend any messages from teammates (broadcasts, replies to our
            # questions, feedback from QA, etc.) so this agent actually sees them
            # during execution. Without this, ask_agent() replies live in the bus
            # but never reach the subclass's execute() prompt.
            inbox = self.get_inbox()
            if inbox:
                full_context = f"{inbox}\n\n{full_context}"

            # Run our internal three-phase protocol
            result = await self._run_protocol(task, full_context)

            # Convert to TaskOutput
            output = TaskOutput(
                task_id=task.task_id,
                description=task.description,
                expected_output=task.expected_output,
                raw=result.raw,
                summary=result.messages[0] if result.messages else result.raw[:200],
                agent=self.agent_id,
                output_format=OutputFormat.JSON if task.output_json else OutputFormat.RAW,
            )

            # Parse structured output if requested
            if task.output_json and result.raw:
                try:
                    parsed = json.loads(result.raw) if isinstance(result.raw, str) else result.raw
                    output.json_dict = parsed
                except (json.JSONDecodeError, TypeError):
                    output.json_dict = result.metadata

            if task.output_pydantic and result.metadata:
                try:
                    output.pydantic = task.output_pydantic(**result.metadata)
                except Exception:
                    pass

            task.output = output
            self.status = AgentStatus.IDLE
            result.duration_seconds = time.time() - start

            log.info(
                "agent_task_complete",
                agent_id=self.agent_id,
                task_id=task.task_id,
                duration=f"{result.duration_seconds:.1f}s",
                tokens=result.input_tokens + result.output_tokens,
            )
            return output

        except Exception as e:
            self.status = AgentStatus.ERROR
            log.error("agent_task_error", agent_id=self.agent_id, error=str(e))

            output = TaskOutput(
                task_id=task.task_id,
                description=task.description,
                expected_output=task.expected_output,
                raw=f"Error: {str(e)}",
                agent=self.agent_id,
            )
            task.output = output
            return output

    # ------------------------------------------------------------------
    # Internal three-phase protocol
    # ------------------------------------------------------------------

    async def _run_protocol(self, task: Any, context: str) -> AgentResult:
        """Run analyze → execute → validate with retries."""
        analysis = await self.analyze(task, context)

        for attempt in range(self.max_retries + 1):
            result = await self.execute(task, context, analysis)

            if not result.success and result.retry_recommended and attempt < self.max_retries:
                analysis["previous_errors"] = result.errors
                continue

            if result.success:
                valid = await self.validate(task, result)
                if valid:
                    return result
                if attempt < self.max_retries:
                    analysis["validation_failed"] = True
                    continue

            return result

        return result  # type: ignore

    @abstractmethod
    async def analyze(self, task: Any, context: str) -> dict[str, Any]:
        """Phase 1: Examine task and context, decide approach."""
        ...

    @abstractmethod
    async def execute(self, task: Any, context: str, analysis: dict[str, Any]) -> AgentResult:
        """Phase 2: Do the work."""
        ...

    async def validate(self, task: Any, result: AgentResult) -> bool:
        """Phase 3: Self-check. Override for custom validation."""
        return result.success and bool(result.raw)

    # ------------------------------------------------------------------
    # Inter-agent communication
    # ------------------------------------------------------------------

    async def send_message(self, to_agent: str, content: str) -> None:
        """Send a direct message to another agent."""
        if self._bus:
            await self._bus.send(self.agent_id, to_agent, content)

    async def ask_agent(self, to_agent: str, question: str) -> str:
        """
        Ask another agent a question and get a response.
        The target agent processes the question via its own Claude instance.

        Example:
            pattern = await self.ask_agent("architect", "What design pattern should I use for caching?")
        """
        if not self._bus:
            return "[No message bus available — agent communication not configured]"
        return await self._bus.ask(self.agent_id, to_agent, question)

    async def broadcast(self, content: str) -> None:
        """Broadcast a message to all agents (e.g., 'Backend API is ready')."""
        if self._bus:
            await self._bus.broadcast(self.agent_id, content)

    async def send_feedback(self, to_agent: str, feedback: str,
                            metadata: dict[str, Any] | None = None) -> None:
        """Send structured feedback to another agent (e.g., QA → Backend about test failures)."""
        if self._bus:
            await self._bus.send_feedback(self.agent_id, to_agent, feedback, metadata)

    def get_inbox(self) -> str:
        """Get formatted inbox of messages from other agents."""
        if not self._bus:
            return ""
        return self._bus.format_inbox(self.agent_id)

    # ------------------------------------------------------------------
    # Routing support
    # ------------------------------------------------------------------

    def can_handle(self, classification: dict[str, Any]) -> float:
        """Confidence score (0.0-1.0) for handling a ticket type."""
        return 0.0
