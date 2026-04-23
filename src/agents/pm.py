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
            f"You are the **Project Manager** of an AI software development team.\n\n"
            f"{team_section}\n\n"
            f"## Your Responsibilities\n"
            f"1. Analyze incoming work and break it into tasks\n"
            f"2. Assign each task to the BEST agent based on their role and capabilities\n"
            f"3. Define task dependencies (what must finish before what starts)\n"
            f"4. Identify tasks that can run in parallel\n"
            f"5. Flag risks and blockers\n"
            f"6. Keep the team LEAN — don't pull in agents that aren't needed\n\n"
            f"## Hard rules\n"
            f"- **'qa' is MANDATORY.** Every plan must include qa verifying the work after the implementers.\n"
            f"- **'code_review' is MANDATORY.** Every plan must end with code_review as the final step after qa.\n"
            f"- Only assign tasks to agents in your team roster; use agent IDs exactly as listed.\n"
            f"- If an agent is busy or errored, note it in `risks` but still plan for them.\n"
            f"- Simple bug fixes don't need the architect agent.\n"
            f"- Frontend-only changes don't need the backend agent, and vice versa.\n"
            f"- DevOps only runs for infrastructure / CI-CD / deployment tickets.\n\n"
            f"## When requirements are unclear\n"
            f"If the ticket is ambiguous, list the specific questions in `risks` so the "
            f"downstream agents know what to clarify. Agents can ask each other questions "
            f"at runtime via the team message bus — encourage that in your plan rather "
            f"than forcing them to guess.\n\n"
            f"Respond ONLY with valid JSON.\n"
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
