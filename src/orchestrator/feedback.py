"""Feedback loop manager for QA -> Dev cycles."""

from __future__ import annotations

from typing import Any

from src.agents.base import AgentResult, BaseAgent
from src.models.context import SharedContext
from src.observability.logging import get_logger

log = get_logger("feedback")


class FeedbackLoop:
    """Manages feedback cycles between QA and dev agents."""

    def __init__(self, max_cycles: int = 3):
        self.max_cycles = max_cycles

    async def run_feedback_cycle(
        self,
        context: SharedContext,
        qa_agent: BaseAgent,
        dev_agents: dict[str, BaseAgent],
        qa_result: AgentResult,
    ) -> AgentResult:
        """
        Run feedback cycles until QA passes or max cycles reached.

        Returns the final QA result.
        """
        current_qa_result = qa_result

        for cycle in range(self.max_cycles):
            if current_qa_result.success:
                log.info("feedback_loop_passed", cycle=cycle)
                return current_qa_result

            log.info(
                "feedback_cycle_start",
                cycle=cycle + 1,
                max_cycles=self.max_cycles,
                failures=len(current_qa_result.errors),
            )

            # Route failures to responsible dev agents
            failures = current_qa_result.metadata.get("test_failures", current_qa_result.errors)
            for failure in failures:
                responsible_agent_id = self._identify_responsible_agent(failure, context)
                if responsible_agent_id and responsible_agent_id in dev_agents:
                    agent = dev_agents[responsible_agent_id]
                    feedback = {
                        "type": "test_failure",
                        "failure": failure,
                        "cycle": cycle + 1,
                    }
                    context.add_feedback(
                        from_agent="qa",
                        to_agent=responsible_agent_id,
                        feedback=feedback,
                        cycle=cycle + 1,
                    )

                    log.info(
                        "feedback_sent",
                        from_agent="qa",
                        to_agent=responsible_agent_id,
                        cycle=cycle + 1,
                    )

                    fix_result = await agent.on_feedback(context, feedback)
                    if fix_result.artifacts:
                        for artifact in fix_result.artifacts:
                            context.add_artifact(artifact)

            # Re-run QA
            current_qa_result = await qa_agent.run(context)

        if not current_qa_result.success:
            log.warning(
                "feedback_loop_exhausted",
                max_cycles=self.max_cycles,
                remaining_errors=current_qa_result.errors,
            )
            current_qa_result.needs_human_review = True

        return current_qa_result

    def _identify_responsible_agent(
        self, failure: Any, context: SharedContext
    ) -> str | None:
        """Determine which dev agent is responsible for a failure."""
        failure_str = str(failure).lower()

        # Simple heuristic based on file paths and keywords
        if any(kw in failure_str for kw in ["frontend", "react", "component", ".tsx", ".jsx", "css"]):
            return "frontend"
        if any(kw in failure_str for kw in ["backend", "api", "endpoint", "database", "model"]):
            return "backend"
        if any(kw in failure_str for kw in ["config", "docker", "ci", "deploy", "infra"]):
            return "devops"

        # Default to backend
        return "backend"
