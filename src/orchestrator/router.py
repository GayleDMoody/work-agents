"""Agent router — classifies tickets and selects the right agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.models.classification import TicketClassification
from src.models.context import SharedContext, TicketContext
from src.models.plan import ExecutionPlan, PlanStep
from src.observability.logging import get_logger

log = get_logger("router")

# Agents that run on EVERY ticket regardless of classification. The router
# re-injects these after Claude responds, so even if the LLM omits them they
# still end up in the final required_agents list. QA + code_review are always
# on so every change is tested and reviewed.
MANDATORY_AGENTS: list[str] = ["product", "pm", "qa", "code_review"]

# Agents whose inclusion is a judgment call — this is where the classifier
# actually adds value.
DISCRETIONARY_AGENTS: list[str] = ["architect", "frontend", "backend", "devops"]


CLASSIFICATION_PROMPT = f"""You are a ticket classifier for a software team's AI agent system.

Analyze the Jira ticket and classify it. Your most important job is deciding which
DISCRETIONARY agents should be pulled in — the mandatory ones are already decided.

## Mandatory agents (ALWAYS run, no need to list them)
{', '.join(MANDATORY_AGENTS)}
- product: captures business requirements
- pm: plans and coordinates the work
- qa: tests whatever gets built
- code_review: final gate before delivery

## Discretionary agents (you decide based on ticket content)
- architect: needed for features with complexity L/XL, 3+ files, or cross-cutting design
- frontend: needed when scope touches UI, UX, React, CSS, client-side code
- backend: needed when scope touches APIs, DB, server logic, integrations
- devops: needed ONLY for infrastructure, CI/CD, deployment, or config changes

Respond with JSON:
{{
    "ticket_type": "feature|bug|refactor|infra|docs",
    "scope": ["frontend", "backend"],
    "complexity": "S|M|L|XL",
    "risk_level": "low|medium|high",
    "required_agents": ["<only the DISCRETIONARY agents you're confident about>"],
    "optional_agents": ["<discretionary agents that might help, low confidence>"],
    "rationale": "one-sentence explanation of agent choices",
    "estimated_files": 5,
    "needs_human_clarification": false,
    "clarification_questions": []
}}

Guidelines:
- Prefer a LEAN team. Don't pull in agents you don't need — fewer agents = faster + cheaper.
- Simple bug fixes often just need one of frontend/backend.
- Pure docs changes may need no discretionary agents at all.
- XL complexity should set needs_human_clarification=true so a human can split the ticket.
"""


class AgentRouter(ClaudeMixin):
    """Classifies tickets and routes them to the right agents."""

    def __init__(self, agents: dict[str, BaseAgent], model: str = "claude-sonnet-4-20250514"):
        self.agents = agents
        self.model = model

    async def classify_ticket(self, context: SharedContext) -> TicketClassification:
        """Use Claude to classify the ticket and determine required agents."""
        ticket = context.ticket
        ticket_text = (
            f"Key: {ticket.key}\n"
            f"Type: {ticket.issue_type}\n"
            f"Priority: {ticket.priority}\n"
            f"Summary: {ticket.summary}\n"
            f"Description: {ticket.description}\n"
            f"Labels: {', '.join(ticket.labels)}\n"
            f"Components: {', '.join(ticket.components)}\n"
        )
        if ticket.acceptance_criteria:
            ticket_text += f"Acceptance Criteria:\n" + "\n".join(f"- {ac}" for ac in ticket.acceptance_criteria)

        try:
            result = await self.call_claude_json(
                messages=[{"role": "user", "content": f"Classify this ticket:\n\n{ticket_text}"}],
                system_prompt=CLASSIFICATION_PROMPT,
                model=self.model,
            )
            meta = result.pop("_meta", {})
            classification = TicketClassification(**{k: v for k, v in result.items() if k in TicketClassification.model_fields})

            # Guarantee mandatory agents are in required_agents regardless of what
            # the classifier returned. The prompt tells Claude to omit them, so we
            # re-inject here as the single source of truth.
            classification.required_agents = self._apply_mandatory(classification.required_agents)

            log.info(
                "ticket_classified",
                ticket_key=ticket.key,
                ticket_type=classification.ticket_type,
                scope=classification.scope,
                complexity=classification.complexity,
                required_agents=classification.required_agents,
            )
            return classification

        except Exception as e:
            log.error("classification_failed", ticket_key=ticket.key, error=str(e))
            # Fallback: conservative classification with backend + architect as a safe default
            return TicketClassification(
                ticket_type="feature",
                scope=["backend"],
                complexity="M",
                risk_level="medium",
                required_agents=self._apply_mandatory(["backend"]),
                optional_agents=["architect"],
                rationale=f"Fallback classification due to error: {str(e)}",
            )

    @staticmethod
    def _apply_mandatory(discretionary: list[str]) -> list[str]:
        """Merge classifier-chosen discretionary agents with the always-on MANDATORY_AGENTS.

        Preserves the canonical pipeline order (product → pm → architect → FE/BE →
        devops → qa → code_review) so downstream ordering logic sees a sensible list.
        """
        canonical_order = ["product", "pm", "architect", "frontend", "backend", "devops", "qa", "code_review"]
        selected = set(MANDATORY_AGENTS) | set(discretionary)
        return [a for a in canonical_order if a in selected]

    def select_agents(self, classification: TicketClassification) -> list[BaseAgent]:
        """Select agents based on classification.

        Mandatory agents (product/pm/qa/code_review) are always selected if registered,
        as a belt-and-suspenders guarantee on top of the classifier-level enforcement.
        """
        selected_ids: list[str] = []
        selected: list[BaseAgent] = []

        def add(agent_id: str, reason: str) -> None:
            if agent_id in selected_ids:
                return
            if agent_id not in self.agents:
                log.warning("agent_not_found", agent_id=agent_id, reason=reason)
                return
            selected_ids.append(agent_id)
            selected.append(self.agents[agent_id])

        # 1. Mandatory agents — always included if registered
        for agent_id in MANDATORY_AGENTS:
            add(agent_id, "mandatory")

        # 2. Classifier-selected required agents
        for agent_id in classification.required_agents:
            add(agent_id, "classifier_required")

        # 3. Optional agents that pass their own can_handle() confidence check
        for agent_id in classification.optional_agents:
            if agent_id in selected_ids or agent_id not in self.agents:
                continue
            agent = self.agents[agent_id]
            confidence = agent.can_handle(classification.model_dump())
            if confidence > 0.5:
                add(agent_id, f"optional_confidence={confidence:.2f}")

        log.info("agents_selected", count=len(selected), ids=selected_ids)
        return selected

    def create_execution_plan(
        self, classification: TicketClassification, agents: list[BaseAgent]
    ) -> ExecutionPlan:
        """Create an ordered execution plan based on agent dependencies."""
        agent_ids = {a.agent_id for a in agents}
        steps: list[PlanStep] = []

        # Define ordering rules
        order_map: dict[str, tuple[int, list[str], bool]] = {
            # agent_id: (priority, depends_on, approval_required)
            "product": (1, [], False),
            "pm": (2, ["product"], False),
            "architect": (3, ["pm"], True),
            "frontend": (4, ["architect"] if "architect" in agent_ids else ["pm"], False),
            "backend": (4, ["architect"] if "architect" in agent_ids else ["pm"], False),
            "qa": (5, [a for a in ["frontend", "backend"] if a in agent_ids] or ["pm"], False),
            "devops": (5, [a for a in ["frontend", "backend"] if a in agent_ids] or ["pm"], False),
            "code_review": (6, ["qa"] if "qa" in agent_ids else ["pm"], False),
        }

        for agent in agents:
            if agent.agent_id in order_map:
                priority, deps, approval = order_map[agent.agent_id]
                valid_deps = [d for d in deps if d in agent_ids]
                steps.append(
                    PlanStep(
                        step_id=agent.agent_id,
                        agent_id=agent.agent_id,
                        description=f"{agent.role}: {agent.goal}",
                        depends_on=valid_deps,
                        is_parallel=priority == 4,  # frontend/backend can run in parallel
                        approval_required=approval,
                    )
                )

        steps.sort(key=lambda s: order_map.get(s.agent_id, (99, [], False))[0])

        return ExecutionPlan(
            steps=steps,
            critical_path=[s.step_id for s in steps if not s.is_parallel],
        )
