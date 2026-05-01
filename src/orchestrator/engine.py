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


# ---------------------------------------------------------------------------
# Run-result wrapper used by the API layer
# ---------------------------------------------------------------------------

class _RunContext:
    """Minimal context shape the API layer reads from a RunResult."""

    def __init__(self, current_phase: str, artifacts: list[dict[str, Any]]):
        self.current_phase = _Phase(current_phase)
        self.artifacts = artifacts


class _Phase:
    """Tiny stand-in for an enum-like phase exposing .value."""
    def __init__(self, value: str):
        self.value = value


class RunResult:
    """High-level result returned by Crew.run()."""
    def __init__(self, success: bool, context: _RunContext, crew_output: Any):
        self.success = success
        self.context = context
        self.crew_output = crew_output


async def _resolve_ticket(ticket_key: str) -> dict[str, Any]:
    """Fetch a ticket from Jira if creds are present; otherwise fall back to a
    fixture or a stub so demos work without a real Jira connection."""
    # Try real Jira — prefer OAuth tokens (works on SSO sites) if connected,
    # otherwise fall back to basic auth (email + API token).
    try:
        from src.settings import Settings
        from src.integrations.jira_client import JiraClient
        from src.integrations.jira_oauth import (
            ensure_fresh_tokens, get_tokens, JiraOAuthConfig,
        )
        s = Settings()
        client: JiraClient | None = None

        # OAuth path
        if s.jira.oauth_client_id and s.jira.oauth_client_secret and get_tokens():
            cfg = JiraOAuthConfig(
                client_id=s.jira.oauth_client_id,
                client_secret=s.jira.oauth_client_secret,
                redirect_uri=s.jira.oauth_redirect_uri,
            )
            tokens = await ensure_fresh_tokens(cfg, verify_ssl=s.jira.verify_ssl)
            if tokens and tokens.cloud_id:
                client = JiraClient(
                    oauth_token=tokens.access_token,
                    cloud_id=tokens.cloud_id,
                    verify_ssl=s.jira.verify_ssl,
                    ca_bundle=s.jira.ca_bundle or None,
                )

        # Basic auth path (legacy / non-SSO sites)
        if client is None and s.jira.server_url and s.jira.email and s.jira.api_token:
            client = JiraClient(
                s.jira.server_url, s.jira.email, s.jira.api_token,
                verify_ssl=s.jira.verify_ssl,
                ca_bundle=s.jira.ca_bundle or None,
            )

        if client is not None:
            ticket = await client.fetch_ticket(ticket_key)
            if ticket:
                log.info("ticket_fetched_from_jira",
                         ticket_key=ticket_key,
                         mode="oauth" if client.is_oauth else "basic")
                return ticket
    except Exception as e:
        log.warning("jira_fetch_failed", ticket_key=ticket_key, error=str(e)[:200])

    # Try a fixture by ticket key
    try:
        import json
        from pathlib import Path
        fixtures_dir = Path("tests/fixtures/sample_tickets")
        if fixtures_dir.exists():
            # Match by key (case-insensitive) or fall back to first fixture
            for fp in fixtures_dir.glob("*.json"):
                data = json.loads(fp.read_text())
                if data.get("key", "").upper() == ticket_key.upper():
                    return data
            # No exact match — use the first fixture as a stand-in for demos
            for fp in sorted(fixtures_dir.glob("*.json")):
                return json.loads(fp.read_text())
    except Exception:
        pass

    # Last-resort stub so the pipeline can still run
    return {
        "key": ticket_key,
        "summary": f"Demo ticket {ticket_key}",
        "description": "No ticket details available — running with a stub payload.",
        "issue_type": "feature",
        "priority": "medium",
        "labels": [],
        "components": [],
        "acceptance_criteria": [],
    }


def _build_run_result(ticket_key: str, ticket: dict[str, Any], crew_output: Any) -> RunResult:
    """Translate a CrewOutput into the (.success / .context.*) shape app.py expects.

    Each task output becomes an artifact carrying its raw text, parsed JSON,
    and any files extracted from common JSON shapes ({"files": [...]}). This
    is what the frontend code/diff viewer renders.
    """
    success = getattr(crew_output, "success", False)
    artifacts: list[dict[str, Any]] = []

    for to in getattr(crew_output, "tasks_output", []) or []:
        raw = getattr(to, "raw", "") or ""
        # Try to parse the agent's output as JSON — most agents respond with structured JSON.
        json_dict = getattr(to, "json_dict", None)
        if json_dict is None and raw:
            try:
                import json as _json
                json_dict = _json.loads(raw)
            except Exception:
                json_dict = None

        # Extract files for code-producing agents (frontend / backend / devops / qa
        # all use a `files` array in their JSON output per their prompts).
        files: list[dict[str, Any]] = []
        if isinstance(json_dict, dict):
            for f in (json_dict.get("files") or []):
                if isinstance(f, dict) and f.get("path"):
                    files.append({
                        "path": f.get("path", ""),
                        "action": f.get("action", "create"),
                        "content": f.get("content", "") or "",
                        "description": f.get("description", "") or "",
                    })
            # QA agent uses `test_files` instead of `files`.
            for f in (json_dict.get("test_files") or []):
                if isinstance(f, dict) and f.get("path"):
                    files.append({
                        "path": f.get("path", ""),
                        "action": f.get("action", "create"),
                        "content": f.get("content", "") or "",
                        "description": f"test file ({f.get('test_count', '?')} tests)",
                    })
            # DevOps agent uses `config_files`.
            for f in (json_dict.get("config_files") or []):
                if isinstance(f, dict) and f.get("path"):
                    files.append({
                        "path": f.get("path", ""),
                        "action": f.get("action", "create"),
                        "content": f.get("content", "") or "",
                        "description": f.get("description", "config file"),
                    })

        agent_id = getattr(to, "agent", "")
        # Pick a useful artifact type for the UI's groupings
        artifact_type = "code" if files else (
            "review" if agent_id == "code_review" else
            "plan" if agent_id == "pm" else
            "design" if agent_id == "architect" else
            "analysis"
        )

        artifacts.append({
            "id": getattr(to, "task_id", ""),
            "artifact_type": artifact_type,
            "name": (getattr(to, "description", "") or "").split("\n", 1)[0][:120],
            "agent_id": agent_id,
            "phase": "execution",
            "raw": raw[:60000],          # cap to keep payloads sane
            "json_dict": json_dict if isinstance(json_dict, (dict, list)) else None,
            "files": files,
            "summary": getattr(to, "summary", "") or "",
        })

    current_phase = "complete" if success else "failed"
    return RunResult(success=success, context=_RunContext(current_phase, artifacts), crew_output=crew_output)


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
        # Optional repo-context block prepended to every agent's context. Set
        # via set_repo_context(...) before run() is called so agents reason
        # about real code instead of writing in a vacuum.
        self._repo_context: str = ""

    def set_repo_context(self, block: str) -> None:
        """Inject a compact 'this is what the repo looks like' block that gets
        prepended to every agent's task context this kickoff."""
        self._repo_context = block or ""

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

            # Prepend the repo context (if the trigger picked one). Comes first
            # so agents see the real codebase before any prior task output.
            if self._repo_context:
                context_str = self._repo_context + "\n\n" + context_str

            # Inject any inter-agent messages into context
            if self._bus:
                inbox = self._bus.format_inbox(agent.agent_id)
                if inbox:
                    context_str = inbox + "\n\n" + context_str

            # Refresh PM's team status view before each task
            self._refresh_pm_status()

            log.info("task_starting", task_id=task.task_id, agent=agent.agent_id,
                     description=task.description[:80])

            self._notify("task_started", {
                "task_id": task.task_id,
                "agent_id": agent.agent_id,
                # Pass through a short version of the task description so the
                # dashboard's busy speech bubble can show what's actually
                # happening instead of a generic "Working..." text.
                "task_description": (task.description or "").split("\n", 1)[0][:140],
            })

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
        return PMAgent(agent_id="manager", model=self.manager_llm or "claude-haiku-4-5-20251001")

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
        """Notify callbacks of an event. Sync callbacks run inline; async ones are
        scheduled on the running event loop."""
        for cb in self.callbacks:
            try:
                result = cb(event_type, data)
                if asyncio.iscoroutine(result):
                    # Async callback — schedule it on the loop without blocking
                    asyncio.create_task(result)
            except Exception as e:
                log.warning("callback_error", event=event_type, error=str(e))

    # ------------------------------------------------------------------
    # API-layer compatibility shims
    # ------------------------------------------------------------------

    def on_event(self, callback: Callable) -> None:
        """Register a callback for crew events. Supports sync and async callbacks.
        Event types emitted: task_started, task_finished, agent_started, agent_finished,
        crew_finished, pipeline_finished. Callback signature: cb(event_type: str, data: dict).
        """
        # Wrap user callbacks to also emit dashboard-friendly aliases
        # (task_started -> agent_started, task_finished -> agent_finished,
        # crew_finished -> pipeline_finished) so consumers can subscribe to
        # whichever name they prefer.
        def _aliased(event_type: str, data: Any) -> Any:
            alias_map = {
                "task_started":   "agent_started",
                "task_finished":  "agent_finished",
                "crew_finished":  "pipeline_finished",
            }
            alias = alias_map.get(event_type)
            payload = data
            # crew_finished fires with the CrewOutput instance — flatten the bits
            # the dashboard cares about into a plain dict.
            if event_type == "crew_finished":
                payload = {
                    "success": getattr(data, "success", False),
                    "duration_seconds": getattr(data, "duration_seconds", 0.0),
                    "cost": {
                        "total_cost_usd":     getattr(getattr(data, "token_usage", None), "total_cost_usd", 0.0),
                        "total_input_tokens": getattr(getattr(data, "token_usage", None), "total_input_tokens", 0),
                        "total_output_tokens":getattr(getattr(data, "token_usage", None), "total_output_tokens", 0),
                    },
                }
            return callback(alias or event_type, payload)
        self.callbacks.append(_aliased)

    async def run(self, ticket_key: str) -> "RunResult":
        """High-level entry point used by the API layer.

        Fetches (or mocks) the ticket, runs the crew with it as input, and returns
        a RunResult exposing .success / .context.current_phase / .context.artifacts
        so the dashboard can render the outcome regardless of whether real Jira /
        GitHub integrations are configured.
        """
        ticket = await _resolve_ticket(ticket_key)
        crew_output = await self.kickoff({
            "ticket_key": ticket_key,
            "ticket_summary": ticket.get("summary", ""),
            "ticket_description": ticket.get("description", ""),
        })
        return _build_run_result(ticket_key, ticket, crew_output)
