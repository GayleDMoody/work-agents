# Work Agents

**A multi-agent software team orchestration system where specialised AI agents collaborate to take Jira tickets from planning to delivery.**

Inspired by [CrewAI](https://github.com/crewAIInc/crewAI)'s `Agent` / `Task` / `Crew` pattern, with a three-phase execution protocol (`analyze` → `execute` → `validate`) built into every agent for quality control, an inter-agent message bus so teammates can actually ask each other questions mid-run, and a gamified isometric dashboard that visualises the pipeline live.

---

## The team

Eight specialised agents form a pipeline. **Product**, **PM**, **QA**, and **Code Review** run on every ticket; the others are pulled in only when the ticket genuinely needs them.

```
            ┌───────────┐
            │  Product  │   Requirements · INVEST · Gherkin ACs · NFRs
            └─────┬─────┘
                  ▼
            ┌───────────┐
            │    PM     │   Execution plan · RAID · critical path
            └─────┬─────┘
                  ▼
            ┌───────────┐
            │ Architect │   Design · ADRs · API contracts · migration strategy
            └─────┬─────┘
       ┌──────────┼──────────┐
       ▼          ▼          ▼
 ┌──────────┐┌────────┐┌──────────┐
 │ Frontend ││Backend ││  DevOps  │   Implementers · run in parallel
 └────┬─────┘└────┬───┘└──────────┘
      └───────┬───┘
              ▼
         ┌───────┐
         │  QA   │   Tests · coverage matrix · non-functional checks
         └───┬───┘
             ▼
      ┌─────────────┐
      │ Code Review │   Final gate · severity-tagged comments
      └─────────────┘
```

Each agent has a production-grade system prompt (120–230 lines each) modelled on how a senior in that role actually works — INVEST / RAID / ADRs / OWASP / WCAG / testing pyramid / SRE principles. See [`prompts/`](./prompts) for the full briefings.

---

## How it works

1. **Classification** — the router reads the Jira ticket and picks *discretionary* agents (architect, frontend, backend, devops). Mandatory agents are force-included so QA and Code Review can never be skipped.
2. **Planning** — PM produces an execution plan with concrete step descriptions, dependencies, parallelisation hints, and risks. If PM forgets QA or code_review, the plan is auto-repaired.
3. **Execution** — the Crew engine runs steps in `SEQUENTIAL` or `HIERARCHICAL` mode, honouring dependencies and running parallel-eligible steps concurrently.
4. **Inter-agent communication** — agents share an `AgentBus` for `send`, `ask` (synchronous Q&A via the target agent's own Claude), `broadcast`, and structured `send_feedback` (e.g., QA → Backend on a test failure). Each agent's inbox is auto-prepended to its context so messages are actually seen, not lost in the bus.
5. **Live dashboard** — WebSocket events stream to a React frontend that shows an isometric pipeline topology with real-time status (idle / busy / error), speech bubbles on busy agents, and animated "data packets" travelling along active connections. Click any agent to open a chat popup backed by that agent's own Claude.

---

## Key features

- **Smart agent selection** — classifier picks only the agents actually needed; mandatory agents enforced at both classification and selection layers
- **Inter-agent Q&A** — agents can `ask_agent("architect", "What pattern should I use for caching?")` mid-run and get a real answer from that agent's Claude
- **Self-repairing plans** — PM's output is validated post-LLM; missing mandatory agents are auto-injected with sensible dependencies
- **Production-grade prompts** — each agent operates with the depth of a 10–15 year practitioner in role, with concrete workflows, checklists, and quality gates
- **Live isometric dashboard** — gamified pipeline visualisation with real-time agent status, polled every 3 seconds with a static topology skeleton as graceful fallback when the backend is offline
- **Chat with any agent** — click an agent node in the dashboard to start a conversation directly with that agent's Claude
- **Full app settings** — per-agent model override, cost limits, approval gates, notifications, theme; persisted to backend and applied to crew execution
- **Connector marketplace** — 17 service connectors (Jira, GitHub, Slack, Datadog, Linear, Sentry, …) with inline SVG brand logos, category filters, and test-connection flow
- **Dark / light / system themes** — `data-theme` attribute on `<html>` drives the switch

---

## Stack

- **Backend**: Python 3.11+ · FastAPI · Anthropic SDK · Pydantic v2 · structlog
- **Frontend**: React 18 · TypeScript (strict) · Vite · plain CSS · TanStack Query · React Router
- **Integrations**: Jira REST (`jira` lib) · GitHub (PyGithub + GitPython)
- **Config**: YAML in `config/` · env vars via pydantic-settings (`WORK_AGENTS_*`) · live settings persisted to `config/app_config.json` via `/api/config`
- **Communication**: WebSocket for real-time pipeline events; REST for everything else

---

## Getting started

### Prerequisites
- Python 3.11+
- Node.js 20+
- An Anthropic API key (`sk-ant-...`)
- Optional: Jira and GitHub credentials for full integration

### Backend

```bash
pip install -e ".[dev]"
cp .env.example .env
# edit .env with your API keys
uvicorn src.api.app:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dashboard polls the backend at http://localhost:8000. If the backend is down, the dashboard falls back to a static topology skeleton and shows "Services disconnected" — by design.

### Triggering a pipeline

From the dashboard HUD:
1. Enter a Jira ticket key (e.g., `PROJ-101`) in the top-left input
2. Click **Deploy**
3. Watch agents go busy, speech bubbles appear, and animated dots flow along active connections

---

## Project structure

```
work-agents/
├── src/
│   ├── agents/              # 8 agent classes + base + registry
│   ├── orchestrator/        # Crew engine, router, agent bus, feedback loops
│   ├── integrations/        # Jira + GitHub clients
│   ├── models/              # Pydantic data models (Task, Artifact, SharedContext, ...)
│   ├── api/                 # FastAPI app + routes + WebSocket
│   └── observability/       # structlog setup
├── frontend/src/
│   ├── pages/               # Dashboard, Pipelines, Agents, Connectors, Settings
│   ├── components/          # IsometricOffice, HUD, ChatPopup, ConnectorLogos, ...
│   ├── api/client.ts        # REST client
│   ├── hooks/useTheme.ts    # Theme switcher
│   └── types.ts             # Shared TS types (mirrors backend Pydantic)
├── prompts/                 # Production-grade agent system prompts
├── config/
│   ├── agents.yaml          # Per-agent model + capability config
│   └── pipeline.yaml        # Pipeline / orchestrator config
└── tests/                   # pytest unit + integration + fixtures
```

---

## Current status

**Working end-to-end**
- Pipeline execution with classifier-driven smart agent selection
- Inter-agent messaging — agents ask each other questions and see the replies on their next turn
- Live dashboard with clean line-connected topology at every viewport size
- Per-agent chat popup backed by each agent's own Claude instance
- App settings persisted to backend and applied to crew execution
- Dark / light theme switcher

**Known gaps / planned**
- Feedback-loop auto-retry (QA failures → implementer re-run) wired in the bus but not yet in the engine
- Pipeline runs are in-memory only — no persistence across restarts
- `ask_agent` is synchronous; no timeout / circuit-breaker yet
- CI pipeline not yet committed (Dockerfile, GitHub Actions, image scanning)

---

## Credits

Built with [Claude Code](https://claude.com/claude-code) using Claude Sonnet 4.6.

Inspired by the CrewAI public API; the internal three-phase protocol, agent bus, and isometric dashboard are original work.
