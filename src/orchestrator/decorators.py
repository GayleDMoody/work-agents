"""
CrewAI-style decorators: @CrewBase, @agent, @task, @crew.

Usage:
    @CrewBase
    class MySoftwareTeam:
        agents_config = 'config/agents.yaml'
        tasks_config = 'config/tasks.yaml'

        @agent
        def backend_dev(self) -> Agent:
            return Agent(role="Backend Developer", ...)

        @task
        def write_code(self) -> Task:
            return Task(description="...", agent=self.backend_dev(), ...)

        @crew
        def crew(self) -> Crew:
            return Crew(agents=self.agents, tasks=self.tasks, ...)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

from src.observability.logging import get_logger

log = get_logger("decorators")


def agent(func: Callable) -> Callable:
    """Mark a method as an agent factory. Collected by @CrewBase."""
    func._is_crew_agent = True
    return func


def task(func: Callable) -> Callable:
    """Mark a method as a task factory. Collected by @CrewBase."""
    func._is_crew_task = True
    return func


def crew(func: Callable) -> Callable:
    """Mark a method as the crew factory. Collected by @CrewBase."""
    func._is_crew_crew = True
    return func


def CrewBase(cls):
    """
    Class decorator that auto-discovers @agent and @task methods.

    Sets up:
        self.agents_config — loaded from YAML (if agents_config attr exists)
        self.tasks_config — loaded from YAML (if tasks_config attr exists)
        self.agents — list of Agent instances from @agent methods
        self.tasks — list of Task instances from @task methods
    """
    original_init = cls.__init__ if hasattr(cls, "__init__") else None

    def new_init(self, *args, **kwargs):
        if original_init and original_init is not object.__init__:
            original_init(self, *args, **kwargs)

        # Load YAML configs
        if hasattr(cls, "agents_config") and isinstance(cls.agents_config, str):
            path = Path(cls.agents_config)
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
                self.agents_config = data.get("agents", data)
            else:
                self.agents_config = {}

        if hasattr(cls, "tasks_config") and isinstance(cls.tasks_config, str):
            path = Path(cls.tasks_config)
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
                self.tasks_config = data.get("tasks", data)
            else:
                self.tasks_config = {}

        # Collect @agent and @task methods. Walk the MRO in reverse + use the
        # class __dict__ directly so methods come out in *source-declaration*
        # order rather than alphabetical (dir() sorts alphabetically, which
        # would put `review_code` before `write_backend_code` and break the
        # pipeline ordering).
        self._agent_methods = []
        self._task_methods = []
        seen: set[str] = set()
        for klass in reversed(type(self).__mro__):
            for attr_name, attr in klass.__dict__.items():
                if attr_name.startswith("_") or attr_name in seen:
                    continue
                if not callable(attr):
                    continue
                if getattr(attr, "_is_crew_agent", False):
                    self._agent_methods.append(attr_name)
                    seen.add(attr_name)
                elif getattr(attr, "_is_crew_task", False):
                    self._task_methods.append(attr_name)
                    seen.add(attr_name)

    @property
    def agents(self) -> list:
        """Auto-collected agents from @agent methods."""
        return [getattr(self, name)() for name in self._agent_methods]

    @property
    def tasks(self) -> list:
        """Auto-collected tasks from @task methods."""
        return [getattr(self, name)() for name in self._task_methods]

    cls.__init__ = new_init
    cls.agents = agents
    cls.tasks = tasks

    return cls
