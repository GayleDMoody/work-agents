"""Agent registry — discovers and instantiates agents from config."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

from src.agents.base import BaseAgent
from src.observability.logging import get_logger

log = get_logger("registry")

# Global registry of agent classes
_AGENT_CLASSES: dict[str, type[BaseAgent]] = {}


def register_agent(agent_id: str):
    """Decorator to register an agent class."""

    def wrapper(cls: type[BaseAgent]):
        _AGENT_CLASSES[agent_id] = cls
        return cls

    return wrapper


class AgentRegistry:
    """Discovers and instantiates agents from configuration."""

    def __init__(self, config_path: str | None = None):
        self.config: dict[str, Any] = {}
        self.agents: dict[str, BaseAgent] = {}

        if config_path:
            self.load_config(config_path)

    def load_config(self, config_path: str) -> None:
        """Load agent configuration from YAML."""
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f)
                self.config = data.get("agents", {})
            log.info("config_loaded", path=config_path, agents=list(self.config.keys()))

    def register(self, agent_id: str, agent: BaseAgent) -> None:
        """Manually register an agent instance."""
        self.agents[agent_id] = agent
        log.info("agent_registered", agent_id=agent_id, role=agent.role)

    def create_agent(self, agent_id: str, **overrides) -> BaseAgent:
        """Create an agent from config and registry."""
        if agent_id in _AGENT_CLASSES:
            config = self.config.get(agent_id, {})
            config.update(overrides)

            cls = _AGENT_CLASSES[agent_id]
            agent = cls(agent_id=agent_id, **config)
            self.agents[agent_id] = agent
            return agent

        raise ValueError(f"Unknown agent: {agent_id}. Available: {list(_AGENT_CLASSES.keys())}")

    def create_all_agents(self) -> dict[str, BaseAgent]:
        """Create all agents defined in config."""
        for agent_id in self.config:
            if agent_id not in self.agents and agent_id in _AGENT_CLASSES:
                try:
                    self.create_agent(agent_id)
                except Exception as e:
                    log.warning("agent_creation_failed", agent_id=agent_id, error=str(e))

        return self.agents

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self.agents.get(agent_id)

    def list_agents(self) -> list[str]:
        return list(self.agents.keys())

    @staticmethod
    def discover_agents() -> None:
        """Import all agent modules to trigger @register_agent decorators."""
        agent_modules = [
            "src.agents.product",
            "src.agents.pm",
            "src.agents.architect",
            "src.agents.frontend",
            "src.agents.backend",
            "src.agents.qa",
            "src.agents.devops",
            "src.agents.code_review",
        ]
        for module_name in agent_modules:
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                log.debug("agent_module_not_found", module=module_name, error=str(e))
