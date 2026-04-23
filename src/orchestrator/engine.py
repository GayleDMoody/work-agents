"""
Crew — CrewAI-style orchestrator.

Usage:
    crew = Crew(
        agents=[product_agent, pm_agent, backend_agent, qa_agent],
        tasks=[analyze_task, plan_task, code_task, test_task],
        process=Process.sequential,
        verbose=True,
    )
    result = await crew.kickoff(inputs={"ticket_key": "PROJ-101"})
"""

from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import Any, Callable, Optional

from src.agents.base import AgentStatus, BaseAgent
from src.models.crew_output import CrewOutput, TokenUsage
from src.models.task import Task, TaskOutput
from src.observability.cost_tracker import CostTracker
from src.observability.logging import get_logger

log = get_logger("crew")


class Process(str, Enum):
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"


class Crew:
    """
    CrewAI-compatible Crew that coordinates agents executing tasks.

    Process types:
        - sequential: Tasks execute in order, each receiving prior outputs as context
        - hierarchical: A manager agent dynamically delegates tasks to the crew
    """

    def __init__(
        self,
        agents: list[BaseAgent] | None = None,
        tasks: list[Task] | None = None,
        process: Process = Process.SEQUENTIAL,
        verbose: bool = False,
        memory: bool = False,
        cache: bool = True,
        max_rpm: int | None = None,
        manager_llm: str | None = None,
        manager_agent: BaseAgent | None = None,
        callbacks: list[Callable] | None = None,
    ):
        self.agents = agents or []
        self.tasks = tasks or []
        self.process = process
        self.verbose = verbose
        self.memory = memory
        self.cache = cache
        self.max_rpm = max_rpm
        self.manager_llm = manager_llm
        self.manager_agent = manager_agent
        self.callbacks = callbacks or []

        # Internal state
        self._agent_map: dict[str, BaseAgent] = {a.agent_id: a for a in self.agents}
        self._bus: Any = None  # AgentBus, created on kickoff
        self._cost_tracker: CostTracker | None = None

    # ------------------------------------------------------------------
    # Public API — matches CrewAI
    # ------------------------------------------------------------------

    async def kickoff(self, inputs: dict[str, Any] | None = None) -> CrewOutput:
        """
        Execute the crew's tasks. Main entry point.

        Args:
            inputs: Variables to interpolate into task descriptions.
                    e.g. {"ticket_key": "PROJ-101", "description": "..."}

        Returns:
            CrewOutput with raw output, structured data, and token usage.
        """
        run_id = str(uuid.uuid4())[:8]
        start = time.time()
        self._cost_tracker = CostTracker(run_id=run_id)
        inputs = inputs or {}

        log.info("crew_kickoff", run_id=run_id, process=self.process.value,
                 agents=len(self.agents), tasks=len(self.tasks))

        # Set up inter-agent communication bus
        self._setup_bus()

        # Give the PM agent full team awareness
        self._equip_pm()

        # Interpolate inputs into task descriptions
        tasks = self._interpolate_tasks(inputs)

        try:
            if self.process == Process.SEQUENTIAL:
                tasks_output = await self._run_sequential(tasks, run_id)
            else:
                tasks_output = await self._run_hierarchical(tasks, inputs, run_id)

            # Build CrewOutput from the last task's output
            final_output = tasks_output[-1] if tasks_output else TaskOutput(
                task_id="none", description="No tasks", expected_output="", raw=""
            )

            result = CrewOutput(
                raw=final_output.raw,
                pydantic=final_output.pydantic,
                json_dict=final_output.json_dict,
                tasks_output=tasks_output,
                token_usage=self._build_token_usage(),
                success=True,
                duration_seconds=time.time() - start,
                run_id=run_id,
            )

            # Attach the message log
            if self._bus:
                result.agent_messages = self._bus.get_full_log()

        except Exception as e:
            log.error("crew_failed", run_id=run_id, error=str(e))
            result = CrewOutput(
                raw=f"Crew execution failed: {str(e)}",
                success=False,
                duration_seconds=time.time() - start,
                run_id=run_id,
            )

        log.info(
            "crew_finished",
            run_id=run_id,
            success=result.success,
            duration=f"{result.duration_seconds:.1f}s",
            tasks_completed=len(result.tasks_output),
        )

        for cb in self.callbacks:
            try:
                cb("crew_finished", result)
            except Exception:
                pass

        return result

    async def akickoff(self, inputs: dict[str, Any] | None = None) -> CrewOutput:
        """Async alias for kickoff (CrewAI compat)."""
        return await self.kickoff(inputs)

    def kickoff_sync(self, inputs: dict[str, Any] | None = None) -> CrewOutput:
        """Synchronous wrapper for kickoff."""
        return asyncio.run(self.kickoff(inputs))

    # ------------------------------------------------------------------
    # Sequential process
    # ------------------------------------------------------------------

    async def _run_sequential(self, tasks: list[Task], run_id: str) -> list[TaskOutput]:
        """Execute tasks in order, auto-passing context from prior tasks."""
        outputs: list[TaskOutput] = []

        for i, task in enumerate(tasks):
            agent = task.agent
            if not agent:
                log.warning("task_no_agent", task_id=task.task_id, description=task.description[:60])
                continue

            # Auto-context: all previous task outputs
            if not task.context and i > 0:
                task.context = tasks[:i]

            context_str = task.get_context_str()

            # Inject any inter-agent messages into context
            if self._bus:
                inbox = self._bus.format_inbox(agent.agent_id)
                if inbox:
                    context_str = inbox + "\n\n" + context_str

            # Refresh PM's team status view before each task
            self._refresh_pm_status()

            log.info("task_starting", task_id=task.task_id, agent=agent.agent_id,
                     description=task.description[:80])

            self._notify("task_started", {"task_id": task.task_id, "agent_id": agent.agent_id})

            output = await agent.execute_task(task, context_str)
            outputs.append(output)

            self._notify("task_finished", {
                "task_id": task.task_id,
                "agent_id": agent.agent_id,
                "success": bool(output.raw and not output.raw.startswith("Error:")),
            })

            if self.verbose:
                log.info("task_output", task_id=task.task_id, raw=output.raw[:200])

        return outputs

    # ------------------------------------------------------------------
    # Hierarchical process
    # ------------------------------------------------------------------

    async def _run_hierarchical(
        self, tasks: list[Task], inputs: dict[str, Any], run_id: str
    ) -> list[TaskOutput]:
        """
        Manager agent coordinates the crew, delegating tasks dynamically.
        Falls back to sequential if no manager is configured.
        """
        if not self.manager_agent and not self.manager_llm:
            log.warning("hierarchical_no_manager", fallback="sequential")
            return await self._run_sequential(tasks, run_id)

        # In hierarchical mode, the manager decides task order and assignment
        # For now, use the manager to create an execution plan, then run it
        manager = self.manager_agent or self._create_default_manager()
        outputs: list[TaskOutput] = []

        for task in tasks:
            # If task has no agent, manager assigns one
            if not task.agent:
                task.agent = self._find_best_agent(task)

            if not task.agent:
                log.warning("no_agent_for_task", task_id=task.task_id)
                continue

            # Build context from completed tasks
            context_str = "\n".join(
                f"[{o.agent}]: {o.raw[:500]}" for o in outputs
            )

            output = await task.agent.execute_task(task, context_str)
            outputs.append(output)

        return outputs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _setup_bus(self) -> None:
        """Create the inter-agent message bus and connect all agents."""
        from src.orchestrator.bus import AgentBus
        self._bus = AgentBus()
        self._bus.register_all(self.agents)
        for agent in self.agents:
            agent._bus = self._bus
        log.info("agent_bus_ready", agents=len(self.agents))

    def _refresh_pm_status(self) -> None:
        """Update PM agents with current team status."""
        from src.agents.pm import PMAgent
        for agent in self.agents:
            if isinstance(agent, PMAgent):
                agent.refresh_team_status(self.agents)

    def _equip_pm(self) -> None:
        """Give any PM agent in the crew full team awareness."""
        from src.agents.pm import PMAgent
        for agent in self.agents:
            if isinstance(agent, PMAgent):
                agent.set_team(self.agents)

        # Also equip the manager agent in hierarchical mode
        if self.manager_agent and isinstance(self.manager_agent, PMAgent):
            self.manager_agent.set_team(self.agents)

    def _interpolate_tasks(self, inputs: dict[str, Any]) -> list[Task]:
        """Replace {variable} placeholders in task descriptions with input values."""
        for task in self.tasks:
            for key, value in inputs.items():
                task.description = task.description.replace(f"{{{key}}}", str(value))
                task.expected_output = task.expected_output.replace(f"{{{key}}}", str(value))
        return self.tasks

    def _find_best_agent(self, task: Task) -> BaseAgent | None:
        """Pick the best agent for a task based on role/capability matching."""
        desc_lower = task.description.lower()
        for agent in self.agents:
            role_lower = agent.role.lower()
            if any(kw in desc_lower for kw in role_lower.split()):
                return agent
        return self.agents[0] if self.agents else None

    def _create_default_manager(self) -> BaseAgent:
        """Create a default manager agent for hierarchical process."""
        # Import here to avoid circular imports
        from src.agents.pm import PMAgent
        return PMAgent(agent_id="manager", model=self.manager_llm or "claude-sonnet-4-20250514")

    def _build_token_usage(self) -> TokenUsage:
        """Build token usage from cost tracker."""
        if not self._cost_tracker:
            return TokenUsage()
        summary = self._cost_tracker.summary()
        return TokenUsage(
            total_input_tokens=summary.get("total_input_tokens", 0),
            total_output_tokens=summary.get("total_output_tokens", 0),
            total_cost_usd=summary.get("total_cost_usd", 0.0),
            by_agent={
                agent_id: {"cost": round(cost, 4)}
                for agent_id, cost in summary.get("cost_by_agent", {}).items()
            },
        )

    def _notify(self, event_type: str, data: dict[str, Any]) -> None:
        """Notify callbacks of an event."""
        for cb in self.callbacks:
            try:
                cb(event_type, data)
            except Exception:
                pass
