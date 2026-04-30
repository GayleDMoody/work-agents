"""
GitHub OAuth flow for repository access.

Same shape as src/integrations/jira_oauth.py — register an OAuth app at
https://github.com/settings/developers (Authorization callback URL pointed at
http://localhost:8000/api/github/oauth/callback), drop the Client ID + Client
Secret into .env (WORK_AGENTS_GITHUB_OAUTH_CLIENT_ID / _SECRET) and the
Connectors page wires the rest.

GitHub OAuth uses 2LO (web flow) — there's no refresh token, but the access
token doesn't expire by default. Scopes default to "repo" (read+write code
plus issues + pulls); narrow to "public_repo" if you only need public repos.
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from src.observability.logging import get_logger

log = get_logger("github_oauth")

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"

DEFAULT_SCOPES = ["repo", "read:user"]

_TOKEN_FILE = Path("config/github_oauth_tokens.json")


@dataclass
class GitHubOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8000/api/github/oauth/callback"
    scopes: list[str] = field(default_factory=lambda: list(DEFAULT_SCOPES))


@dataclass
class GitHubOAuthTokens:
    access_token: str
    token_type: str = "bearer"
    scope: str = ""
    user_login: str = ""    # GitHub username
    user_avatar: str = ""   # avatar URL for display


_pending_state: dict[str, dict[str, Any]] = {}
_tokens: GitHubOAuthTokens | None = None


def _save_tokens_to_disk() -> None:
    if _tokens is None:
        return
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps(asdict(_tokens), indent=2))
        try: _TOKEN_FILE.chmod(0o600)
        except Exception: pass
    except Exception as e:
        log.warning("github_oauth_persist_failed", error=str(e)[:120])


def _load_tokens_from_disk() -> GitHubOAuthTokens | None:
    if not _TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(_TOKEN_FILE.read_text())
        return GitHubOAuthTokens(**data)
    except Exception as e:
        log.warning("github_oauth_load_failed", error=str(e)[:120])
        return None


def _delete_tokens_from_disk() -> None:
    try:
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
    except Exception:
        pass


_tokens = _load_tokens_from_disk()
if _tokens:
    log.info("github_oauth_tokens_restored", login=_tokens.user_login)


def get_tokens() -> GitHubOAuthTokens | None:
    return _tokens


def is_connected() -> bool:
    return _tokens is not None


def build_authorize_url(cfg: GitHubOAuthConfig) -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    _pending_state[state] = {"created_at": time.time()}
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": " ".join(cfg.scopes),
        "state": state,
        "allow_signup": "false",
    }
    url = f"{AUTHORIZE_URL}?{urlencode(params)}"
    log.info("github_oauth_authorize_url_built", scopes=cfg.scopes)
    return url, state


async def exchange_code_for_tokens(
    cfg: GitHubOAuthConfig, code: str, state: str, *, verify_ssl: bool = True,
) -> GitHubOAuthTokens:
    if state not in _pending_state:
        raise ValueError("state_mismatch_or_expired")
    _pending_state.pop(state, None)

    payload = {
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "code": code,
        "redirect_uri": cfg.redirect_uri,
    }
    async with httpx.AsyncClient(verify=verify_ssl, timeout=15.0) as http:
        # GitHub's token endpoint accepts JSON when Accept: application/json
        r = await http.post(TOKEN_URL, json=payload, headers={"Accept": "application/json"})
        if r.status_code != 200:
            log.error("github_oauth_token_exchange_failed", status=r.status_code, body=r.text[:200])
            raise ValueError(f"token_exchange_failed: {r.status_code}")
        data = r.json()
        if data.get("error"):
            raise ValueError(f"github_error: {data.get('error_description') or data.get('error')}")

    tokens = GitHubOAuthTokens(
        access_token=data["access_token"],
        token_type=data.get("token_type", "bearer"),
        scope=data.get("scope", ""),
    )

    # Look up the user so we can show "Connected as @username" in the UI.
    async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as http:
        r2 = await http.get(USER_URL, headers={
            "Authorization": f"Bearer {tokens.access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if r2.status_code == 200:
            user = r2.json()
            tokens.user_login = user.get("login", "")
            tokens.user_avatar = user.get("avatar_url", "")

    global _tokens
    _tokens = tokens
    _save_tokens_to_disk()
    log.info("github_oauth_tokens_stored", login=tokens.user_login)
    return tokens


def disconnect() -> None:
    global _tokens
    _tokens = None
    _delete_tokens_from_disk()
    log.info("github_oauth_disconnected")
