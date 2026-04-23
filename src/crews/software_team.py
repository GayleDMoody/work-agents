"""
SoftwareTeamCrew — the main crew definition using @CrewBase decorators.

Usage:
    team = SoftwareTeamCrew()
    result = await team.crew().kickoff(inputs={
        "ticket_key": "PROJ-101",
        "ticket_summary": "Add user profile page",
        "ticket_description": "...",
    })
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.claude_mixin import ClaudeMixin
from src.models.task import Task
from src.orchestrator.decorators import CrewBase, agent, task, crew
from src.orchestrator.engine import Crew, Process
from src.observability.logging import get_logger

log = get_logger("software_team")


@CrewBase
class SoftwareTeamCrew:
    """AI software team that processes Jira tickets from planning to delivery."""

    agents_config = "config/agents.yaml"

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @agent
    def product_analyst(self) -> BaseAgent:
        from src.agents.product import ProductAgent
        return ProductAgent()

    @agent
    def project_manager(self) -> BaseAgent:
        from src.agents.pm import PMAgent
        return PMAgent()

    @agent
    def architect(self) -> BaseAgent:
        from src.agents.architect import ArchitectAgent
        return ArchitectAgent()

    @agent
    def frontend_dev(self) -> BaseAgent:
        from src.agents.frontend import FrontendAgent
        return FrontendAgent()

    @agent
    def backend_dev(self) -> BaseAgent:
        from src.agents.backend import BackendAgent
        return BackendAgent()

    @agent
    def qa_engineer(self) -> BaseAgent:
        from src.agents.qa import QAAgent
        return QAAgent()

    @agent
    def devops_engineer(self) -> BaseAgent:
        from src.agents.devops import DevOpsAgent
        return DevOpsAgent()

    @agent
    def code_reviewer(self) -> BaseAgent:
        from src.agents.code_review import CodeReviewAgent
        return CodeReviewAgent()

    # ------------------------------------------------------------------
    # Tasks — define the pipeline as a task sequence
    # ------------------------------------------------------------------

    @task
    def analyze_requirements(self) -> Task:
        return Task(
            description=(
                "Analyze the Jira ticket and produce structured requirements.\n"
                "Ticket: {ticket_key}\n"
                "Summary: {ticket_summary}\n"
                "Description: {ticket_description}"
            ),
            expected_output=(
                "JSON with: acceptance_criteria, clarification_questions, "
                "user_stories, edge_cases, risks, is_well_defined"
            ),
            agent=self.product_analyst(),
            output_json=dict,
        )

    @task
    def create_plan(self) -> Task:
        return Task(
            description=(
                "Create an execution plan for this ticket based on the requirements analysis.\n"
                "Ticket: {ticket_key} — {ticket_summary}\n"
                "Determine which agents are needed and in what order."
            ),
            expected_output=(
                "JSON with: plan_summary, steps (agent, task, depends_on), "
                "risks, estimated_complexity"
            ),
            agent=self.project_manager(),
            output_json=dict,
        )

    @task
    def design_architecture(self) -> Task:
        return Task(
            description=(
                "Design the technical approach for implementing this ticket.\n"
                "Ticket: {ticket_key} — {ticket_summary}\n"
                "Description: {ticket_description}"
            ),
            expected_output=(
                "JSON with: approach, files_to_create, files_to_modify, "
                "interfaces, patterns, dependencies"
            ),
            agent=self.architect(),
            output_json=dict,
        )

    @task
    def write_backend_code(self) -> Task:
        return Task(
            description=(
                "Write backend code to implement the ticket.\n"
                "Ticket: {ticket_key} — {ticket_summary}\n"
                "Description: {ticket_description}"
            ),
            expected_output="JSON with: files (path, content, action), summary, dependencies_added",
            agent=self.backend_dev(),
            output_json=dict,
        )

    @task
    def write_frontend_code(self) -> Task:
        return Task(
            description=(
                "Write frontend code to implement the ticket.\n"
                "Ticket: {ticket_key} — {ticket_summary}\n"
                "Description: {ticket_description}"
            ),
            expected_output="JSON with: files (path, content, action), summary, dependencies_added",
            agent=self.frontend_dev(),
            output_json=dict,
            async_execution=True,
        )

    @task
    def write_tests(self) -> Task:
        return Task(
            description=(
                "Write tests for the code changes.\n"
                "Ticket: {ticket_key}"
            ),
            expected_output=(
                "JSON with: test_plan, test_files (path, content, test_count), "
                "edge_cases_covered, coverage_estimate"
            ),
            agent=self.qa_engineer(),
            output_json=dict,
        )

    @task
    def review_code(self) -> Task:
        return Task(
            description=(
                "Review all code changes and tests for quality, security, and correctness.\n"
                "Ticket: {ticket_key}"
            ),
            expected_output=(
                "JSON with: decision (approve/changes_requested), summary, "
                "comments, security_issues, test_coverage_assessment"
            ),
            agent=self.code_reviewer(),
            output_json=dict,
        )

    # ------------------------------------------------------------------
    # Crew
    # ------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.SEQUENTIAL,
            verbose=True,
        )


def create_full_crew() -> Crew:
    """Factory function to create the full software team crew."""
    team = SoftwareTeamCrew()
    return team.crew()


def create_backend_bug_crew() -> Crew:
    """Smaller crew for backend-only bug fixes."""
    team = SoftwareTeamCrew()
    return Crew(
        agents=[team.product_analyst(), team.project_manager(),
                team.backend_dev(), team.qa_engineer(), team.code_reviewer()],
        tasks=[
            team.analyze_requirements(),
            team.create_plan(),
            team.write_backend_code(),
            team.write_tests(),
            team.review_code(),
        ],
        process=Process.SEQUENTIAL,
        verbose=True,
    )
