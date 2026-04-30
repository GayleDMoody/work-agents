"""FastAPI application for the Work Agents dashboard."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
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
                    # Update agent status in AGENTS list
                    for a in AGENTS:
                        if a["id"] == agent_id:
                            a["status"] = "busy"
                    run["events"].append({
                        "type": event_type,
                        "timestamp": run["updated_at"],
                        "message": f"{agent_id} started",
                        "agent_id": agent_id,
                    })
                elif event_type == "agent_finished":
                    agent_id = data.get("agent_id", "")
                    for a in AGENTS:
                        if a["id"] == agent_id:
                            a["status"] = "idle"
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
            result = await orchestrator.run(req.ticket_key)

            run["status"] = "completed" if result.success else "failed"
            run["current_phase"] = result.context.current_phase.value
            run["artifacts"] = [
                {"id": a.get("id", ""), "artifact_type": a.get("artifact_type", ""), "name": a.get("name", ""), "agent_id": a.get("agent_id", ""), "phase": a.get("phase", "")}
                for a in result.context.artifacts
            ]
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
