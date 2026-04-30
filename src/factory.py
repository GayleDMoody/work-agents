"""Factory module — creates crews with live config applied."""

from __future__ import annotations

from src.observability.logging import get_logger
from src.orchestrator.engine import Crew, Process

log = get_logger("factory")


def _get_app_config() -> dict:
    """Load the live app config (from API cache or disk fallback)."""
    try:
        from src.api.app import get_live_config
        return get_live_config()
    except Exception:
        pass

    # Fallback: read from disk
    import json
    from pathlib import Path
    config_path = Path("config/app_config.json")
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except Exception:
            pass
    return {}


def _apply_config_to_crew(crew: Crew, config: dict) -> Crew:
    """Apply app config settings to a crew and its agents."""

    # Process type
    process_type = config.get("processType", "sequential")
    crew.process = Process.HIERARCHICAL if process_type == "hierarchical" else Process.SEQUENTIAL

    # Verbose
    crew.verbose = config.get("verbose", False)

    # Agent model overrides
    agent_models = config.get("agentModels", {})
    default_model = config.get("defaultModel", "claude-haiku-4-5-20251001")

    for agent in crew.agents:
        # Apply per-agent model override, or fall back to default
        override = agent_models.get(agent.agent_id, "")
        if override:
            agent.model = override
        else:
            agent.model = default_model

        # Apply max retries
        agent.max_retries = config.get("maxRetries", 2)

        # Apply verbose
        agent.verbose = config.get("verbose", False)

    log.info(
        "config_applied",
        process=crew.process.value,
        default_model=default_model,
        overrides={k: v for k, v in agent_models.items() if v},
        max_retries=config.get("maxRetries", 2),
        feedback_loops=config.get("maxFeedbackLoops", 3),
    )

    return crew


def create_crew(ticket_type: str = "full") -> Crew:
    """
    Create a Crew with live config applied.

    Args:
        ticket_type: "full" (all agents), "backend_bug", or "frontend_only"
    """
    from src.crews.software_team import (
        create_full_crew,
        create_backend_bug_crew,
    )

    if ticket_type == "backend_bug":
        crew = create_backend_bug_crew()
    else:
        crew = create_full_crew()

    # Apply live config
    config = _get_app_config()
    if config:
        crew = _apply_config_to_crew(crew, config)

    log.info("crew_created", type=ticket_type, agents=len(crew.agents), tasks=len(crew.tasks))
    return crew


# Keep backward compatibility
def create_orchestrator(config_path: str = "config/agents.yaml", **kwargs) -> Crew:
    """Legacy alias — creates a full crew."""
    return create_crew("full")
