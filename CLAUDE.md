# Work Agents - Multi-Agent Software Team Orchestration

## Project Overview
A production-grade system where specialized AI agents (product, PM, architect, frontend, backend, QA, devops, code review) collaborate to process Jira tickets from planning to delivery. Built with a CrewAI-inspired architecture.

## Architecture
- **Orchestrator pattern**: Central engine sequences agents through pipeline phases
- **Pipeline phases**: INTAKE -> CLASSIFICATION -> PLANNING -> [ARCHITECTURE] -> EXECUTION -> TESTING -> REVIEW -> [DEPLOYMENT] -> COMPLETE
- **Agent protocol**: Every agent implements analyze() -> execute() -> validate()
- **Smart routing**: Not all agents run for every ticket — router selects based on classification

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Anthropic SDK, structlog
- **Frontend**: React + TypeScript (Vite), plain CSS (no Tailwind)
- **Integrations**: Jira REST API (`jira` lib), GitHub (GitPython + PyGithub)
- **Config**: YAML files in `config/`, env vars via pydantic-settings

## Key Directories
- `src/agents/` — Agent base class and implementations
- `src/orchestrator/` — Pipeline engine, router, feedback loops
- `src/integrations/` — Jira and GitHub clients
- `src/models/` — Pydantic data models (SharedContext, Artifact, etc.)
- `src/api/` — FastAPI app serving the dashboard
- `prompts/` — System prompts for each agent (markdown)
- `config/` — YAML configuration (agents, pipeline)
- `frontend/` — React dashboard app

## Dev Commands
```bash
# Backend
pip install -e ".[dev]"
uvicorn src.api.app:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Tests
pytest tests/unit/ -v
pytest tests/integration/ -v

# Linting
ruff check src/
mypy src/
```

## Style Conventions
- Pydantic v2 BaseModel for all data models
- async/await throughout (sync libs wrapped in asyncio.to_thread)
- structlog for all logging
- Type hints on all functions
- Agent prompts stored as external .md files in `prompts/`
