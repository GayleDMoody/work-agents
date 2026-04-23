"""PM Agent — the team coordinator who knows every agent and orchestrates work."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import AgentCapability, AgentResult, AgentStatus, BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.agents.registry import register_agent
from src.observability.logging import get_logger

log = get_logger("agent.pm")


@register_agent("pm")
class PMAgent(BaseAgent, ClaudeMixin):
    """
    The Project Manager has full awareness of the team:
    - Knows every agent's role, capabilities, and current status
    - Can see which agents are busy, idle, or errored
    - Creates execution plans that reference specific agents by name
    - In hierarchical mode, dynamically assigns tasks to agents
    """

    def __init__(self, agent_id: str = "pm", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="Project Manager",
            goal="Coordinate the AI software team by creating execution plans and assigning the right agents to the right tasks",
            backstory=(
                "You are a senior project manager who leads an AI software team. "
                "You have complete visibility into every team member's role, capabilities, "
                "current workload, and performance history. You create efficient execution "
                "plans by matching tasks to the agents best suited for them. You understand "
                "dependencies between tasks and can parallelize work when possible."
            ),
            capabilities=[AgentCapability.PLANNING],
            **{k: v for k, v in kwargs.items() if k in ("model", "max_retries", "system_prompt_file", "llm", "verbose")},
        )
        # Team roster — populated by the Crew before execution
        self._team: list[dict[str, Any]] = []

    def set_team(self, agents: list[BaseAgent]) -> None:
        """Register the full team roster so PM knows who's available."""
        self._team = []
        for agent in agents:
            if agent.agent_id == self.agent_id:
                continue  # Don't include self
            self._team.append({
                "id": agent.agent_id,
                "role": agent.role,
                "goal": agent.goal,
                "capabilities": [c.value for c in agent.capabilities],
                "status": agent.status.value,
                "model": agent.model,
            })
        log.info("pm_team_set", team_size=len(self._team), agents=[a["id"] for a in self._team])

    def _build_team_roster_str(self) -> str:
        """Build a formatted string describing the team for the prompt."""
        if not self._team:
            return "No team members registered."

        lines = ["## Your Team\n"]
        for agent in self._team:
            status_icon = {"idle": "🟢", "busy": "🔵", "error": "🔴"}.get(agent["status"], "⚪")
            lines.append(
                f"- **{agent['id']}** ({agent['role']}) {status_icon} {agent['status']}\n"
                f"  Goal: {agent['goal']}\n"
                f"  Capabilities: {', '.join(agent['capabilities'])}"
            )
        return "\n".join(lines)

    def refresh_team_status(self, agents: list[BaseAgent]) -> None:
        """Update the status of all agents (call before each planning cycle)."""
        agent_map = {a.agent_id: a for a in agents}
        for entry in self._team:
            agent = agent_map.get(entry["id"])
            if agent:
                entry["status"] = agent.status.value

    @property
    def system_prompt(self) -> str:
        team_section = self._build_team_roster_str()
        return (
            "# Project Manager Agent\n\n"
            "## Identity\n"
            "You are a senior engineering manager / technical program manager with 12+ years "
            "of experience running cross-functional delivery. You've been a working engineer, "
            "so you know when an estimate is nonsense. You've shipped through incidents and run "
            "post-mortems. You know the most expensive bug is the one the team committed to "
            "building without understanding.\n\n"
            "## Mission\n"
            "Turn a ready ticket into a concrete, minimal, parallel-where-possible execution "
            "plan that the rest of the team can run without further ambiguity. You optimise "
            "for throughput and predictability, not for looking busy.\n\n"
            f"{team_section}\n\n"
            "## Core principles\n"
            "1. **Lean team > big team.** Fewer agents = less coordination = faster delivery. "
            "Don't pull in architect for a one-line bug fix.\n"
            "2. **QA and code_review are non-negotiable.** Every plan ends with qa, then "
            "code_review. No exceptions. The system will add them if you forget, but forgetting "
            "signals you're not thinking about quality gates.\n"
            "3. **Parallelise ruthlessly.** Frontend and backend for different API endpoints "
            "can run in parallel. So can devops work that doesn't depend on code shape.\n"
            "4. **Be explicit about dependencies.** `depends_on` is how the engine decides "
            "what runs when. Wrong dependencies = serialised work that should parallelise, "
            "or race conditions that should serialise.\n"
            "5. **Surface unknowns.** If the ticket is still ambiguous in places, list the "
            "questions in `risks` / `open_questions` and suggest which downstream agent should "
            "resolve them (often via ask_agent). Do not paper over gaps.\n\n"
            "## Planning workflow\n"
            "1. Sanity-check: if the product analysis marked is_well_defined=false, your plan "
            "is short — a clarification task followed by a re-plan placeholder. Don't push through ambiguity.\n"
            "2. Decide which discretionary agents are needed. For each one NOT included, put the "
            "reason in `agents_not_needed`:\n"
            "   - architect — needed for complexity L/XL, 3+ files, cross-module changes, or new patterns\n"
            "   - frontend — needed when UI, UX, React, CSS, or client-side code is touched\n"
            "   - backend — needed for APIs, DB, server logic, auth, background jobs, integrations\n"
            "   - devops — needed for infra, CI/CD, env vars, secrets, observability infra\n"
            "3. Break work into concrete steps with specific task descriptions "
            "(not 'work on backend' — 'Add POST /api/subscriptions/{id}/cancel that locks the row, "
            "records a CancellationEvent, returns effective end date').\n"
            "4. Identify the critical path (longest chain of dependencies) and parallelise every "
            "step whose depends_on is actually satisfied earlier.\n"
            "5. Enumerate RAID: Risks (with severity + mitigation + owner), Assumptions, Issues, "
            "Dependencies. Unmitigated risks are complaints, not plans.\n"
            "6. Size it (S/M/L/XL). If XL, first step is a decomposition task, not implementation. "
            "When uncertain between two sizes, choose the larger.\n\n"
            "## Parallelisation rules\n"
            "- Frontend + backend can run in parallel if the API contract is locked (architect finished) "
            "OR if they're independent features.\n"
            "- QA cannot start until the implementers it covers have finished.\n"
            "- Code review always runs last, after QA.\n"
            "- DevOps for CI/env-vars can often run alongside implementation.\n"
            "- Multiple architect steps rarely parallelise — design decisions serialise.\n\n"
            "## Hard rules\n"
            "- **'qa' is MANDATORY.** Every plan must include qa verifying the work after implementers.\n"
            "- **'code_review' is MANDATORY.** Every plan must end with code_review as the final step after qa.\n"
            "- Only assign tasks to agents in your team roster; use agent IDs exactly as listed.\n"
            "- If an agent is busy or errored, note it in `risks` but still plan for them.\n"
            "- Simple bug fixes don't need the architect agent.\n"
            "- Frontend-only changes don't need the backend agent, and vice versa.\n"
            "- DevOps only runs for infrastructure / CI-CD / deployment tickets.\n\n"
            "## When requirements are unclear\n"
            "If the ticket is ambiguous, list specific questions in `risks` or `open_questions` so "
            "downstream agents know what to clarify. Agents can ask each other at runtime via the "
            "team message bus — encourage that in your plan rather than forcing them to guess.\n\n"
            "## Output contract\n"
            "Respond ONLY with valid JSON containing: plan_summary, steps (each with step_id, agent, "
            "task, depends_on[], parallel, acceptance), agents_needed[], agents_not_needed[{agent, "
            "reason}], critical_path[step_id...], can_parallelize, parallel_groups[[...]], risks "
            "[{risk, severity, mitigation, owner}], assumptions[], open_questions[{question, should_ask}], "
            "estimated_complexity (S|M|L|XL), notes.\n\n"
            "## Quality bar (self-check)\n"
            "- Every step has a specific, testable task description\n"
            "- depends_on correctly populated (no orphans, no cycles)\n"
            "- QA and code_review present and at the end\n"
            "- agents_not_needed explains every exclusion\n"
            "- Critical path <= 5 steps for S/M tickets\n"
            "- Every risk has severity + mitigation\n"
        )

    async def analyze(self, task: Any, context: str) -> dict[str, Any]:
        return {
            "description": task.description,
            "expected_output": getattr(task, "expected_output", ""),
            "has_context": bool(context),
            "team_size": len(self._team),
            "available_agents": [a["id"] for a in self._team if a["status"] != "error"],
            "busy_agents": [a["id"] for a in self._team if a["status"] == "busy"],
            "errored_agents": [a["id"] for a in self._team if a["status"] == "error"],
        }

    async def execute(self, task: Any, context: str, analysis: dict[str, Any]) -> AgentResult:
        prompt = f"Create an execution plan for this work:\n\n**Task**: {task.description}\n\n"

        if context:
            prompt += f"**Prior context from other agents**:\n{context}\n\n"

        if analysis.get("expected_output"):
            prompt += f"**Expected output format**: {analysis['expected_output']}\n\n"

        # Add real-time team status
        prompt += f"**Available agents**: {', '.join(analysis.get('available_agents', []))}\n"
        if analysis.get("busy_agents"):
            prompt += f"**Currently busy**: {', '.join(analysis['busy_agents'])}\n"
        if analysis.get("errored_agents"):
            prompt += f"**Currently errored**: {', '.join(analysis['errored_agents'])}\n"
        prompt += "\n"

        prompt += (
            'Provide JSON:\n'
            '{"plan_summary": "One-line summary of the plan", '
            '"steps": [{"step_id": "1", "agent": "agent_id", "task": "What this agent should do", "depends_on": [], "parallel": false}], '
            '"agents_needed": ["list of agent IDs that will be used"], '
            '"agents_not_needed": ["list of agent IDs NOT needed and why"], '
            '"risks": ["Potential blockers or issues"], '
            '"estimated_complexity": "S|M|L|XL", '
            '"can_parallelize": true, '
            '"parallel_groups": [["agent1", "agent2"]], '
            '"notes": "Any additional considerations"}'
        )

        try:
            result = await self.call_claude_json(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.system_prompt,
                model=self.model,
            )
            meta = result.pop("_meta", {})

            # Validate that referenced agents actually exist
            known_ids = {a["id"] for a in self._team}
            plan_agents = set(result.get("agents_needed", []))
            unknown = plan_agents - known_ids
            if unknown:
                result["warnings"] = [f"Unknown agents referenced: {unknown}"]
                log.warning("pm_unknown_agents", unknown=list(unknown))

            # Repair the plan if the LLM dropped a mandatory agent. qa and code_review
            # are always required; inject them if missing so downstream phases always
            # get tested and reviewed regardless of what the model produced.
            self._ensure_mandatory_agents(result, known_ids)

            return AgentResult(
                agent_id=self.agent_id,
                success=True,
                raw=json.dumps(result),
                messages=[
                    f"Plan: {len(result.get('steps', []))} steps, {len(result.get('agents_needed', []))} agents",
                    f"Complexity: {result.get('estimated_complexity', '?')}",
                ],
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

    # Mandatory agents that every plan must include, in pipeline order
    MANDATORY_AGENTS: tuple[str, ...] = ("qa", "code_review")

    def _ensure_mandatory_agents(self, plan: dict[str, Any], known_ids: set[str]) -> None:
        """Patch the plan in-place so mandatory agents always appear.

        Adds a step + agents_needed entry for any mandatory agent the LLM omitted.
        Dependencies are wired so qa depends on whatever code-writing agents are in the
        plan, and code_review depends on qa.
        """
        steps: list[dict[str, Any]] = plan.setdefault("steps", [])
        agents_needed: list[str] = plan.setdefault("agents_needed", [])
        existing_step_agents = {s.get("agent") for s in steps if s.get("agent")}

        implementers = [a for a in ("architect", "frontend", "backend", "devops") if a in existing_step_agents]

        for mandatory in self.MANDATORY_AGENTS:
            if mandatory in existing_step_agents or mandatory not in known_ids:
                continue

            if mandatory == "qa":
                depends_on = implementers or [a for a in existing_step_agents if a not in ("product", "pm")] or ["pm"]
                task_desc = "Write and run tests covering the implemented changes; report any failures back to the implementers."
            else:  # code_review
                depends_on = ["qa"] if "qa" in existing_step_agents or "qa" in [s.get("agent") for s in steps] else ["pm"]
                task_desc = "Final review of the combined changeset before delivery."

            steps.append({
                "step_id": str(len(steps) + 1),
                "agent": mandatory,
                "task": task_desc,
                "depends_on": depends_on,
                "parallel": False,
            })
            if mandatory not in agents_needed:
                agents_needed.append(mandatory)

            log.info("pm_mandatory_agent_injected", agent=mandatory, reason="missing_from_llm_plan")

    async def validate(self, task: Any, result: AgentResult) -> bool:
        if not result.success:
            return False
        steps = result.metadata.get("steps", [])
        return len(steps) > 0

    def can_handle(self, classification: dict[str, Any]) -> float:
        return 1.0
