"""FastAPI application for the Work Agents dashboard."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from src.observability.logging import setup_logging, get_logger

setup_logging()
log = get_logger("api")

app = FastAPI(
    title="Work Agents API",
    description="Multi-agent software team orchestration system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory state (replaced by real DB/orchestrator in production)
# ---------------------------------------------------------------------------

pipeline_runs: dict[str, dict] = {}
connected_services: dict[str, dict] = {
    "jira": {"connected": False, "server_url": "", "email": "", "api_token": ""},
    "github": {"connected": False, "token": "", "repo": ""},
    "anthropic": {"connected": False, "api_key": "", "model": "claude-haiku-4-5-20251001"},
}
websocket_clients: list[WebSocket] = []


def _autodetect_connections() -> None:
    """Inspect the loaded environment + persisted state and mark any credential-
    backed services as connected so the Connectors page reflects reality on
    page load instead of needing a manual Test Connection click."""
    try:
        from src.settings import Settings
        from src.integrations.jira_oauth import is_connected as jira_oauth_is_connected, get_tokens as jira_oauth_tokens
        s = Settings()

        # Anthropic — present if WORK_AGENTS_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY is set
        import os as _os
        has_anthropic = bool(s.anthropic.api_key) or bool(_os.environ.get("ANTHROPIC_API_KEY"))
        if has_anthropic:
            connected_services["anthropic"]["connected"] = True
            if s.anthropic.api_key:
                connected_services["anthropic"]["api_key"] = "***"  # presence only, never the real value
            connected_services["anthropic"]["model"] = s.anthropic.default_model

        # Jira — OAuth tokens persisted on disk?
        if jira_oauth_is_connected():
            t = jira_oauth_tokens()
            connected_services["jira"]["connected"] = True
            connected_services["jira"]["server_url"] = t.site_url if t else ""
            connected_services["jira"]["email"] = ""
        # Or basic-auth creds in env (legacy / non-SSO sites)
        elif s.jira.server_url and s.jira.email and s.jira.api_token:
            connected_services["jira"]["connected"] = True
            connected_services["jira"]["server_url"] = s.jira.server_url
            connected_services["jira"]["email"] = s.jira.email

        # GitHub — token present in env?
        if s.github.token:
            connected_services["github"]["connected"] = True
            connected_services["github"]["repo"] = s.github.repo
    except Exception as e:
        log.warning("autodetect_connections_failed", error=str(e)[:120])


_autodetect_connections()

# Agent definitions
AGENTS = [
    {
        "id": "product",
        "name": "Product Agent",
        "role": "Product Analyst",
        "description": "Analyzes requirements, writes acceptance criteria, identifies gaps",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["requirements_analysis"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "pm",
        "name": "PM Agent",
        "role": "Project Manager",
        "description": "Creates execution plans, assigns agents, tracks progress",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["planning"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "architect",
        "name": "Architect Agent",
        "role": "Software Architect",
        "description": "Designs technical solutions, defines interfaces and patterns",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["architecture"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "frontend",
        "name": "Frontend Agent",
        "role": "Frontend Developer",
        "description": "Writes React/TypeScript frontend code",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["frontend_code"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "backend",
        "name": "Backend Agent",
        "role": "Backend Developer",
        "description": "Writes Python backend code, APIs, services",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["backend_code"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "qa",
        "name": "QA Agent",
        "role": "QA Engineer",
        "description": "Writes test plans, automated tests, validates quality",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["testing"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "devops",
        "name": "DevOps Agent",
        "role": "DevOps Engineer",
        "description": "Handles CI/CD, deployment configs, infrastructure",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["devops"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
    {
        "id": "code_review",
        "name": "Code Review Agent",
        "role": "Senior Engineer",
        "description": "Reviews PRs for correctness, security, and quality",
        "status": "idle",
        "total_runs": 0,
        "successful_runs": 0,
        "total_cost": 0.0,
        "capabilities": ["code_review"],
        "model": "claude-haiku-4-5-20251001",
        "current_task": "",
    },
]


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class TriggerPipelineRequest(BaseModel):
    ticket_key: str


class UpdateSettingsRequest(BaseModel):
    service: str
    config: dict


class TestConnectionRequest(BaseModel):
    service: str


# ---------------------------------------------------------------------------
# WebSocket for real-time updates
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    websocket_clients.append(ws)
    log.info("websocket_connected", total_clients=len(websocket_clients))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(ws)
        log.info("websocket_disconnected", total_clients=len(websocket_clients))


async def broadcast_event(event_type: str, data: dict):
    """Send real-time update to all connected WebSocket clients."""
    message = json.dumps({"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
    disconnected = []
    for ws in websocket_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        websocket_clients.remove(ws)


# ---------------------------------------------------------------------------
# Live agent-thought stream → WebSocket
# ---------------------------------------------------------------------------
# Subscribe to the in-process thought feed and rebroadcast every event over
# the existing /ws WebSocket. Frontend chat panels listen for type="thought"
# events keyed by agent_id and render each one as a chat bubble.

# Keep recent thoughts in memory so a chat panel that opens AFTER an agent
# has already started can replay the last N messages without losing context.
agent_thoughts: dict[str, list[dict]] = {a["id"]: [] for a in AGENTS}
_THOUGHT_BACKLOG = 50  # per-agent ring buffer

def _on_agent_thought(payload: dict) -> None:
    """Subscriber called by claude_mixin / bus on every agent activity.
    Stores the payload in the per-agent backlog and broadcasts it to all
    connected WebSocket clients."""
    agent_id = payload.get("agent_id", "")
    if not agent_id:
        return
    backlog = agent_thoughts.setdefault(agent_id, [])
    backlog.append(payload)
    if len(backlog) > _THOUGHT_BACKLOG:
        del backlog[: len(backlog) - _THOUGHT_BACKLOG]
    # Schedule the broadcast on the running event loop (callback is sync)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(broadcast_event("agent_thought", payload))
    except RuntimeError:
        pass

try:
    from src.agents.claude_mixin import subscribe_to_thoughts as _sub_thoughts
    _sub_thoughts(_on_agent_thought)
except Exception as _e:
    log.warning("thought_subscription_failed", error=str(_e))


@app.get("/api/agents/{agent_id}/thoughts")
async def get_agent_thoughts(agent_id: str):
    """Return the recent thought-stream backlog for an agent.
    Lets a chat panel that opens mid-pipeline replay the messages already
    emitted by this agent before subscribing to live events."""
    return agent_thoughts.get(agent_id, [])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/dashboard")
async def get_dashboard():
    active_runs = [r for r in pipeline_runs.values() if r["status"] == "running"]
    completed_runs = [r for r in pipeline_runs.values() if r["status"] == "completed"]
    failed_runs = [r for r in pipeline_runs.values() if r["status"] == "failed"]

    total_cost = sum(r.get("total_cost", 0) for r in pipeline_runs.values())
    total_tokens = sum(r.get("total_tokens", 0) for r in pipeline_runs.values())

    busy_agents = sum(1 for a in AGENTS if a["status"] == "busy")

    return {
        "active_pipelines": len(active_runs),
        "completed_pipelines": len(completed_runs),
        "failed_pipelines": len(failed_runs),
        "total_pipelines": len(pipeline_runs),
        "busy_agents": busy_agents,
        "idle_agents": len(AGENTS) - busy_agents,
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "recent_runs": sorted(
            pipeline_runs.values(), key=lambda r: r["created_at"], reverse=True
        )[:10],
        "services": {
            name: {"connected": svc["connected"]} for name, svc in connected_services.items()
        },
    }


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------


@app.get("/api/pipelines")
async def list_pipelines():
    return sorted(pipeline_runs.values(), key=lambda r: r["created_at"], reverse=True)


@app.get("/api/pipelines/{run_id}")
async def get_pipeline(run_id: str):
    if run_id not in pipeline_runs:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return pipeline_runs[run_id]


@app.post("/api/pipelines/trigger")
async def trigger_pipeline(req: TriggerPipelineRequest):
    run_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    run = {
        "id": run_id,
        "ticket_key": req.ticket_key,
        "status": "running",
        "current_phase": "intake",
        "phases": [
            {"name": "intake", "status": "running", "started_at": now},
            {"name": "classification", "status": "pending"},
            {"name": "planning", "status": "pending"},
            {"name": "architecture", "status": "pending"},
            {"name": "execution", "status": "pending"},
            {"name": "testing", "status": "pending"},
            {"name": "review", "status": "pending"},
            {"name": "complete", "status": "pending"},
        ],
        "agents_used": [],
        "artifacts": [],
        "events": [{"type": "pipeline_started", "timestamp": now, "message": f"Pipeline started for {req.ticket_key}"}],
        "total_cost": 0.0,
        "total_tokens": 0,
        "created_at": now,
        "updated_at": now,
        "duration_seconds": 0,
        "feedback_loops": 0,
        "approvals": [],
    }

    pipeline_runs[run_id] = run
    await broadcast_event("pipeline_started", run)
    log.info("pipeline_triggered", run_id=run_id, ticket_key=req.ticket_key)

    # Kick off the orchestrator in the background
    async def _run_pipeline():
        try:
            from src.factory import create_orchestrator

            orchestrator = create_orchestrator()

            # Wire events to update the in-memory run record + websocket
            async def on_event(event_type: str, data: dict):
                run["updated_at"] = datetime.now(timezone.utc).isoformat()
                if event_type == "agent_started":
                    agent_id = data.get("agent_id", "")
                    if agent_id and agent_id not in run["agents_used"]:
                        run["agents_used"].append(agent_id)
                    # Update agent status in AGENTS list — also stash the
                    # current task description so the dashboard speech bubble
                    # can show what the agent is actually working on.
                    task_desc = (data.get("task_description") or "")[:140]
                    for a in AGENTS:
                        if a["id"] == agent_id:
                            a["status"] = "busy"
                            a["current_task"] = task_desc
                    run["events"].append({
                        "type": event_type,
                        "timestamp": run["updated_at"],
                        "message": f"{agent_id} started",
                        "agent_id": agent_id,
                        "task_description": task_desc,
                    })
                elif event_type == "agent_finished":
                    agent_id = data.get("agent_id", "")
                    for a in AGENTS:
                        if a["id"] == agent_id:
                            a["status"] = "idle"
                            a["current_task"] = ""
                            a["total_runs"] += 1
                            if data.get("success"):
                                a["successful_runs"] += 1
                    run["events"].append({
                        "type": event_type,
                        "timestamp": run["updated_at"],
                        "message": f"{agent_id} finished ({'ok' if data.get('success') else 'failed'})",
                        "agent_id": agent_id,
                    })
                elif event_type == "pipeline_finished":
                    run.update({
                        "total_cost": data.get("cost", {}).get("total_cost_usd", 0),
                        "total_tokens": data.get("cost", {}).get("total_input_tokens", 0) + data.get("cost", {}).get("total_output_tokens", 0),
                        "duration_seconds": data.get("duration_seconds", 0),
                    })
                await broadcast_event(event_type, data)

            orchestrator.on_event(on_event)
            run_started = datetime.now(timezone.utc)
            result = await orchestrator.run(req.ticket_key)

            run["status"] = "completed" if result.success else "failed"
            run["current_phase"] = result.context.current_phase.value
            # Keep the full enriched artifact (including files / json_dict / raw)
            # so the code viewer can render the agent's actual output.
            run["artifacts"] = list(result.context.artifacts)

            # Pull token usage / cost from the underlying CrewOutput if available.
            crew_out = getattr(result, "crew_output", None)
            tu = getattr(crew_out, "token_usage", None) if crew_out else None
            if tu is not None:
                run["total_cost"] = round(getattr(tu, "total_cost_usd", 0.0) or 0.0, 4)
                run["total_tokens"] = (
                    int(getattr(tu, "total_input_tokens", 0) or 0)
                    + int(getattr(tu, "total_output_tokens", 0) or 0)
                )
            run["duration_seconds"] = round(
                (datetime.now(timezone.utc) - run_started).total_seconds(), 2
            )
            run["updated_at"] = datetime.now(timezone.utc).isoformat()

            await broadcast_event("pipeline_complete", {"run_id": run_id, "success": result.success})

        except Exception as e:
            log.error("pipeline_error", run_id=run_id, error=str(e))
            run["status"] = "failed"
            run["events"].append({
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": str(e),
            })
            await broadcast_event("pipeline_error", {"run_id": run_id, "error": str(e)})

    asyncio.create_task(_run_pipeline())
    return run


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@app.get("/api/agents")
async def list_agents():
    return AGENTS


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    for agent in AGENTS:
        if agent["id"] == agent_id:
            return agent
    raise HTTPException(status_code=404, detail="Agent not found")


# ---------------------------------------------------------------------------
# Settings / Service Connections
# ---------------------------------------------------------------------------


@app.get("/api/settings")
async def get_settings():
    # Return settings with secrets masked
    safe = {}
    for service, config in connected_services.items():
        safe[service] = {}
        for key, value in config.items():
            if key in ("api_token", "token", "api_key") and value:
                safe[service][key] = value[:4] + "..." + value[-4:] if len(value) > 8 else "****"
            else:
                safe[service][key] = value
    return safe


@app.post("/api/settings")
async def update_settings(req: UpdateSettingsRequest):
    if req.service not in connected_services:
        raise HTTPException(status_code=400, detail=f"Unknown service: {req.service}")

    connected_services[req.service].update(req.config)
    log.info("settings_updated", service=req.service)
    return {"status": "ok", "service": req.service}


@app.post("/api/settings/test")
async def test_connection(req: TestConnectionRequest):
    """Test connection to an external service."""
    service = req.service
    config = connected_services.get(service)

    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown service: {service}")

    if service == "jira":
        if not config.get("server_url") or not config.get("api_token"):
            return {"success": False, "message": "Missing Jira server URL or API token"}
        try:
            from jira import JIRA
            jira = await asyncio.to_thread(
                JIRA, server=config["server_url"], basic_auth=(config["email"], config["api_token"])
            )
            await asyncio.to_thread(jira.myself)
            connected_services[service]["connected"] = True
            return {"success": True, "message": "Connected to Jira successfully"}
        except Exception as e:
            connected_services[service]["connected"] = False
            return {"success": False, "message": f"Jira connection failed: {str(e)}"}

    elif service == "github":
        if not config.get("token"):
            return {"success": False, "message": "Missing GitHub token"}
        try:
            from github import Github
            gh = Github(config["token"])
            user = await asyncio.to_thread(lambda: gh.get_user().login)
            connected_services[service]["connected"] = True
            return {"success": True, "message": f"Connected to GitHub as {user}"}
        except Exception as e:
            connected_services[service]["connected"] = False
            return {"success": False, "message": f"GitHub connection failed: {str(e)}"}

    elif service == "anthropic":
        if not config.get("api_key"):
            return {"success": False, "message": "Missing Anthropic API key"}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config["api_key"])
            response = await asyncio.to_thread(
                client.messages.create,
                model=config.get("model", "claude-haiku-4-5-20251001"),
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            connected_services[service]["connected"] = True
            return {"success": True, "message": "Connected to Anthropic API successfully"}
        except Exception as e:
            connected_services[service]["connected"] = False
            return {"success": False, "message": f"Anthropic connection failed: {str(e)}"}

    return {"success": False, "message": f"Unknown service: {service}"}


# ---------------------------------------------------------------------------
# App Config (persisted to disk)
# ---------------------------------------------------------------------------

APP_CONFIG_PATH = Path("config/app_config.json")

# Default app config
_DEFAULT_APP_CONFIG = {
    "theme": "dark",
    "defaultModel": "claude-haiku-4-5-20251001",
    "verbose": False,
    "processType": "sequential",
    "maxFeedbackLoops": 3,
    "maxRetries": 2,
    "taskTimeoutSeconds": 300,
    "maxConcurrentPipelines": 5,
    "costLimitPerRun": 5.0,
    "costLimitMonthly": 200.0,
    "warnAtPercent": 80,
    "requireArchitectureApproval": True,
    "requirePreMergeApproval": True,
    "requireDeploymentApproval": False,
    "autoApproveSmallTickets": True,
    "notifyOnComplete": True,
    "notifyOnFailure": True,
    "notifyOnApprovalNeeded": True,
    "notificationChannel": "in-app",
    "agentModels": {
        "product": "", "pm": "", "architect": "", "frontend": "",
        "backend": "", "qa": "", "devops": "", "code_review": "",
    },
}


def _load_app_config() -> dict:
    """Load app config from disk, falling back to defaults."""
    if APP_CONFIG_PATH.exists():
        try:
            with open(APP_CONFIG_PATH) as f:
                saved = json.loads(f.read())
            # Merge with defaults so new keys are always present
            merged = {**_DEFAULT_APP_CONFIG, **saved}
            # Ensure agentModels has all keys
            merged["agentModels"] = {**_DEFAULT_APP_CONFIG["agentModels"], **merged.get("agentModels", {})}
            return merged
        except Exception as e:
            log.warning("config_load_error", error=str(e))
    return {**_DEFAULT_APP_CONFIG}


def _save_app_config(config: dict) -> None:
    """Persist app config to disk and update in-memory cache."""
    global _app_config
    _app_config = config
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(APP_CONFIG_PATH, "w") as f:
        f.write(json.dumps(config, indent=2))
    log.info("app_config_saved")


# In-memory cache
_app_config: dict = _load_app_config()


@app.get("/api/config")
async def get_app_config():
    """Get the full app configuration."""
    return _app_config


@app.post("/api/config")
async def update_app_config(req: dict):
    """Update app configuration. Merges with existing config."""
    global _app_config
    _app_config.update(req)
    # Ensure agentModels merge properly
    if "agentModels" in req:
        _app_config["agentModels"] = {**_DEFAULT_APP_CONFIG["agentModels"], **req["agentModels"]}
    _save_app_config(_app_config)
    return {"status": "ok"}


@app.post("/api/config/reset")
async def reset_app_config():
    """Reset app config to defaults."""
    global _app_config
    _app_config = {**_DEFAULT_APP_CONFIG}
    _save_app_config(_app_config)
    return {"status": "ok"}


def get_live_config() -> dict:
    """Access the live config from other modules (e.g., Crew)."""
    return _app_config


# ---------------------------------------------------------------------------
# Agent Chat
# ---------------------------------------------------------------------------

# Per-agent conversation histories: { agent_id: [ {role, content, timestamp} ] }
agent_conversations: dict[str, list[dict]] = {}

# Agent instances cache (lazy-loaded)
_agent_instances: dict[str, Any] = {}


def _get_agent_instance(agent_id: str):
    """Lazy-load an agent instance for chat."""
    if agent_id not in _agent_instances:
        from src.agents.registry import AgentRegistry
        AgentRegistry.discover_agents()
        from src.agents.registry import _AGENT_CLASSES
        if agent_id in _AGENT_CLASSES:
            _agent_instances[agent_id] = _AGENT_CLASSES[agent_id](agent_id=agent_id)
        else:
            return None
    return _agent_instances[agent_id]


class ChatRequest(BaseModel):
    message: str


@app.post("/api/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, req: ChatRequest):
    """Send a message to an agent and get a response."""
    # Validate agent exists
    agent_info = None
    for a in AGENTS:
        if a["id"] == agent_id:
            agent_info = a
            break
    if not agent_info:
        raise HTTPException(status_code=404, detail="Agent not found")

    now = datetime.now(timezone.utc).isoformat()

    # Initialize conversation if needed
    if agent_id not in agent_conversations:
        agent_conversations[agent_id] = []

    # Add user message
    agent_conversations[agent_id].append({
        "role": "user",
        "content": req.message,
        "timestamp": now,
    })

    # Get agent instance and call Claude
    agent_instance = _get_agent_instance(agent_id)
    if not agent_instance:
        # Fallback: return a canned response if agent can't be instantiated
        response_text = (
            f"Hi! I'm the {agent_info['name']} ({agent_info['role']}). "
            f"{agent_info['description']}. "
            f"I'm not connected to the Claude API right now, but once configured "
            f"I can help you with {', '.join(agent_info['capabilities'])}."
        )
    else:
        try:
            from src.agents.claude_mixin import ClaudeMixin

            # Build conversation messages for Claude
            messages = []
            for msg in agent_conversations[agent_id]:
                if msg["role"] in ("user", "assistant"):
                    messages.append({"role": msg["role"], "content": msg["content"]})

            result = await agent_instance.call_claude(
                messages=messages,
                system_prompt=agent_instance.system_prompt,
                model=agent_instance.model,
                max_tokens=2048,
            )
            response_text = result["content"]
        except Exception as e:
            log.error("chat_error", agent_id=agent_id, error=str(e))
            response_text = (
                f"I'm the {agent_info['name']}. I couldn't reach the Claude API: {str(e)[:100]}. "
                f"Make sure your Anthropic API key is configured in Settings."
            )

    # Add assistant response
    agent_conversations[agent_id].append({
        "role": "assistant",
        "content": response_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "agent_id": agent_id,
        "response": response_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/agents/{agent_id}/chat")
async def get_chat_history(agent_id: str):
    """Get conversation history with an agent."""
    return agent_conversations.get(agent_id, [])


@app.delete("/api/agents/{agent_id}/chat")
async def clear_chat_history(agent_id: str):
    """Clear conversation history with an agent."""
    agent_conversations[agent_id] = []
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Notes board (agent investigation notes + threaded comments)
# ---------------------------------------------------------------------------

class NoteCreateRequest(BaseModel):
    author: str = "user"
    title: str
    body: str = ""
    tags: list[str] = []
    ticket_key: str = ""
    pipeline_run_id: str = ""


class CommentCreateRequest(BaseModel):
    author: str = "user"
    body: str


@app.get("/api/notes")
async def list_notes_endpoint(ticket_key: str = ""):
    from src.api import notes as notes_store
    return notes_store.list_notes(ticket_key or None)


@app.get("/api/notes/{note_id}")
async def get_note_endpoint(note_id: str):
    from src.api import notes as notes_store
    note = notes_store.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="note_not_found")
    return note


@app.post("/api/notes")
async def add_note_endpoint(req: NoteCreateRequest):
    from src.api import notes as notes_store
    note = notes_store.add_note(
        author=req.author, title=req.title, body=req.body,
        tags=req.tags, ticket_key=req.ticket_key, pipeline_run_id=req.pipeline_run_id,
    )
    await broadcast_event("note_added", note)
    return note


@app.post("/api/notes/{note_id}/comments")
async def add_comment_endpoint(note_id: str, req: CommentCreateRequest):
    from src.api import notes as notes_store
    comment = notes_store.add_comment(note_id, author=req.author, body=req.body)
    if comment is None:
        raise HTTPException(status_code=404, detail="note_not_found")
    await broadcast_event("note_commented", {"note_id": note_id, "comment": comment})
    return comment


@app.delete("/api/notes/{note_id}")
async def delete_note_endpoint(note_id: str):
    from src.api import notes as notes_store
    if not notes_store.delete_note(note_id):
        raise HTTPException(status_code=404, detail="note_not_found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Jira OAuth 2.0 (3LO) flow
# ---------------------------------------------------------------------------

def _jira_oauth_config():
    """Build a JiraOAuthConfig from current settings, or raise 400 if not configured."""
    from src.integrations.jira_oauth import JiraOAuthConfig
    from src.settings import Settings
    s = Settings()
    if not (s.jira.oauth_client_id and s.jira.oauth_client_secret):
        raise HTTPException(
            status_code=400,
            detail="Jira OAuth not configured. Set WORK_AGENTS_JIRA_OAUTH_CLIENT_ID and "
                   "WORK_AGENTS_JIRA_OAUTH_CLIENT_SECRET in .env, then restart.",
        )
    return JiraOAuthConfig(
        client_id=s.jira.oauth_client_id,
        client_secret=s.jira.oauth_client_secret,
        redirect_uri=s.jira.oauth_redirect_uri,
    ), s.jira.verify_ssl


@app.get("/api/jira/oauth/start")
async def jira_oauth_start():
    """Return the Atlassian authorize URL the browser should open."""
    from src.integrations.jira_oauth import build_authorize_url
    cfg, _verify = _jira_oauth_config()
    url, _state = build_authorize_url(cfg)
    return {"authorize_url": url}


@app.get("/api/jira/oauth/redirect")
async def jira_oauth_redirect():
    """Convenience endpoint: build the authorize URL and HTTP-302 to it.
    Useful for one-click sign-in from a button or a manually-pasted URL."""
    from src.integrations.jira_oauth import build_authorize_url
    cfg, _verify = _jira_oauth_config()
    url, _state = build_authorize_url(cfg)
    return RedirectResponse(url, status_code=302)


@app.get("/api/jira/oauth/callback", response_class=HTMLResponse)
async def jira_oauth_callback(code: str = "", state: str = "", error: str = ""):
    """Atlassian redirects here after the user authorizes the app.

    Exchanges the auth code for tokens and renders a small "you can close
    this tab" page that pings the parent window to refresh.
    """
    if error:
        log.error("oauth_callback_error", error=error)
        return HTMLResponse(_oauth_result_html(False, f"Atlassian returned error: {error}"))
    if not code or not state:
        return HTMLResponse(_oauth_result_html(False, "Missing code or state in callback."))

    from src.integrations.jira_oauth import exchange_code_for_tokens
    cfg, verify_ssl = _jira_oauth_config()
    try:
        tokens = await exchange_code_for_tokens(cfg, code, state, verify_ssl=verify_ssl)
    except Exception as e:
        log.error("oauth_callback_exchange_failed", error=str(e))
        return HTMLResponse(_oauth_result_html(False, f"Token exchange failed: {str(e)[:160]}"))

    # Mark Jira as connected in the live services map
    connected_services["jira"]["connected"] = True
    connected_services["jira"]["server_url"] = tokens.site_url
    connected_services["jira"]["email"] = ""

    return HTMLResponse(_oauth_result_html(
        True,
        f"Connected to {tokens.site_url}. You can close this tab — the dashboard will pick it up automatically.",
    ))


@app.get("/api/jira/oauth/status")
async def jira_oauth_status():
    """Lightweight endpoint the frontend can poll to know if OAuth completed."""
    from src.integrations.jira_oauth import get_tokens
    t = get_tokens()
    if not t:
        return {"connected": False}
    return {
        "connected": True,
        "site_url": t.site_url,
        "cloud_id": t.cloud_id,
        "expires_in_seconds": max(0, int(t.expires_at - __import__("time").time())),
    }


@app.post("/api/jira/oauth/disconnect")
async def jira_oauth_disconnect():
    from src.integrations.jira_oauth import disconnect
    disconnect()
    connected_services["jira"]["connected"] = False
    return {"status": "disconnected"}


@app.get("/api/jira/ticket/{ticket_key}")
async def jira_fetch_ticket(ticket_key: str):
    """Fetch a single Jira ticket using the configured auth (OAuth preferred,
    basic fallback). Returns the ticket as a dict, or {error: ...}.
    Useful for verifying the integration before triggering a full pipeline."""
    from src.orchestrator.engine import _resolve_ticket
    try:
        ticket = await _resolve_ticket(ticket_key)
        # _resolve_ticket falls back to a stub when no source works — flag that
        # so callers can tell real Jira hits from stub fallbacks.
        is_stub = (ticket.get("description", "") or "").startswith("No ticket details available")
        return {
            "source": "stub" if is_stub else "jira_or_fixture",
            "ticket": ticket,
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


def _oauth_result_html(success: bool, message: str) -> str:
    color = "#3fb950" if success else "#f85149"
    icon = "✓" if success else "✗"
    title = "Jira connected" if success else "Jira connection failed"
    return f"""<!doctype html>
<html><head><title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
         background: #050710; color: #c9d1d9; display: grid; place-items: center;
         min-height: 100vh; margin: 0; padding: 20px; }}
  .card {{ background: #0d1117; border: 1px solid #1e2229; border-radius: 12px;
           padding: 32px; max-width: 480px; box-shadow: 0 20px 60px rgba(0,0,0,.5); }}
  .icon {{ font-size: 48px; color: {color}; margin-bottom: 8px; }}
  h1 {{ font-size: 18px; margin: 8px 0; }}
  p {{ font-size: 14px; color: #8b949e; line-height: 1.5; }}
  .hint {{ margin-top: 18px; padding: 12px; background: #161b22; border-radius: 8px;
           font-size: 12px; color: #6e7681; }}
</style></head>
<body><div class="card">
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <div class="hint">This window will close automatically in a moment.</div>
</div>
<script>
  // Notify the opener (the dashboard) that auth completed, then close.
  try {{ window.opener && window.opener.postMessage({{type: 'jira-oauth', success: {str(success).lower()} }}, '*'); }} catch(e) {{}}
  setTimeout(() => {{ try {{ window.close(); }} catch(e) {{}} }}, 2500);
</script>
</body></html>"""
