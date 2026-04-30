"""
Atlassian OAuth 2.0 (3LO) flow for Jira Cloud.

Why this exists:
    Atlassian Cloud sites enforced behind SSO/SAML (most enterprise installs)
    won't accept basic-auth API tokens. The supported alternative is OAuth 2.0
    3LO — the user signs in via their corporate IdP, grants the app the
    requested scopes, and the app receives an access token + refresh token.

Flow:
    1. /api/jira/oauth/start
        Builds the Atlassian authorize URL with client_id + scopes + a CSRF
        state nonce. The browser is redirected there.
    2. User signs in (corporate SSO) and approves the scopes.
    3. Atlassian redirects to the configured callback URL with ?code=… &state=…
    4. /api/jira/oauth/callback
        Verifies state, exchanges the code for an access_token + refresh_token,
        looks up the cloud_id (Atlassian site ID) via api.atlassian.com/oauth/token/accessible-resources,
        and stores everything in the in-memory token store.
    5. Pipeline runs use JiraClient.from_oauth(...) which sends Bearer auth to
        https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/…

This module owns the token plumbing; the FastAPI routes in app.py call into it.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from src.observability.logging import get_logger

log = get_logger("jira_oauth")

# Persisted-token file. Survives backend restarts so users don't have to
# re-authorize on every dev-server reload. Gitignored.
_TOKEN_FILE = Path("config/jira_oauth_tokens.json")


AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
TOKEN_URL = "https://auth.atlassian.com/oauth/token"
RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

# Default scopes — read-only suffices for fetching tickets the pipeline runs against.
# Add `write:jira-work` if/when agents should post results back as comments.
DEFAULT_SCOPES = [
    "read:jira-work",
    "read:jira-user",
    "offline_access",          # required to receive a refresh_token
]


@dataclass
class JiraOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8000/api/jira/oauth/callback"
    scopes: list[str] = field(default_factory=lambda: list(DEFAULT_SCOPES))
    audience: str = "api.atlassian.com"


@dataclass
class JiraOAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: float       # epoch seconds; renew before this
    cloud_id: str = ""      # Atlassian site ID
    site_url: str = ""      # https://moodysanalytics.atlassian.net

    @property
    def is_expired(self) -> bool:
        # 60-second skew so we refresh slightly early
        return time.time() >= self.expires_at - 60


# In-memory state. Tokens are also persisted to a gitignored JSON file so they
# survive backend restarts (otherwise users have to re-auth every reload).
_pending_state: dict[str, dict[str, Any]] = {}   # state-nonce -> {"created_at": ...}
_tokens: JiraOAuthTokens | None = None


def _save_tokens_to_disk() -> None:
    if _tokens is None:
        return
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps(asdict(_tokens), indent=2))
        # Best-effort permissions tighten (owner read/write only)
        try:
            _TOKEN_FILE.chmod(0o600)
        except Exception:
            pass
    except Exception as e:
        log.warning("oauth_token_persist_failed", error=str(e)[:120])


def _load_tokens_from_disk() -> JiraOAuthTokens | None:
    if not _TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(_TOKEN_FILE.read_text())
        return JiraOAuthTokens(**data)
    except Exception as e:
        log.warning("oauth_token_load_failed", error=str(e)[:120])
        return None


def _delete_tokens_from_disk() -> None:
    try:
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
    except Exception:
        pass


# Try to restore from disk on module import
_tokens = _load_tokens_from_disk()
if _tokens:
    log.info("oauth_tokens_restored_from_disk", cloud_id=_tokens.cloud_id, site=_tokens.site_url)


def get_tokens() -> JiraOAuthTokens | None:
    """Return the currently stored tokens (or None if not connected)."""
    return _tokens


def is_connected() -> bool:
    return _tokens is not None


def build_authorize_url(cfg: JiraOAuthConfig) -> tuple[str, str]:
    """Generate the Atlassian authorize URL the user is redirected to.

    Returns (url, state). Caller stores `state` so the callback can verify it.
    """
    state = secrets.token_urlsafe(24)
    _pending_state[state] = {"created_at": time.time()}

    params = {
        "audience": cfg.audience,
        "client_id": cfg.client_id,
        "scope": " ".join(cfg.scopes),
        "redirect_uri": cfg.redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    url = f"{AUTHORIZE_URL}?{urlencode(params)}"
    log.info("oauth_authorize_url_built", scopes=cfg.scopes)
    return url, state


async def exchange_code_for_tokens(
    cfg: JiraOAuthConfig,
    code: str,
    state: str,
    *,
    verify_ssl: bool = True,
) -> JiraOAuthTokens:
    """Exchange an authorization code for access + refresh tokens.

    Raises ValueError if state mismatches or token exchange fails.
    """
    if state not in _pending_state:
        raise ValueError("state_mismatch_or_expired")
    _pending_state.pop(state, None)

    payload = {
        "grant_type": "authorization_code",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "code": code,
        "redirect_uri": cfg.redirect_uri,
    }
    async with httpx.AsyncClient(verify=verify_ssl, timeout=15.0) as http:
        r = await http.post(TOKEN_URL, json=payload)
        if r.status_code != 200:
            log.error("oauth_token_exchange_failed", status=r.status_code, body=r.text[:300])
            raise ValueError(f"token_exchange_failed: {r.status_code} {r.text[:200]}")
        data = r.json()

    expires_at = time.time() + int(data.get("expires_in", 3600))
    tokens = JiraOAuthTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_at=expires_at,
    )

    # Look up the cloud_id (the Atlassian "site" identifier) — required for
    # the api.atlassian.com/ex/jira/{cloud_id}/... base URL.
    async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as http:
        r2 = await http.get(
            RESOURCES_URL,
            headers={"Authorization": f"Bearer {tokens.access_token}", "Accept": "application/json"},
        )
        if r2.status_code == 200:
            resources = r2.json()
            for res in resources:
                if "jira" in (res.get("scopes") or []) or any("jira" in s for s in (res.get("scopes") or [])):
                    tokens.cloud_id = res.get("id", "")
                    tokens.site_url = res.get("url", "")
                    break
            if not tokens.cloud_id and resources:
                # Fall back to the first resource — typical for single-site users
                tokens.cloud_id = resources[0].get("id", "")
                tokens.site_url = resources[0].get("url", "")
        else:
            log.warning("oauth_resources_lookup_failed", status=r2.status_code)

    global _tokens
    _tokens = tokens
    _save_tokens_to_disk()
    log.info("oauth_tokens_stored", cloud_id=tokens.cloud_id, site=tokens.site_url)
    return tokens


async def refresh_tokens(cfg: JiraOAuthConfig, *, verify_ssl: bool = True) -> JiraOAuthTokens:
    """Use the refresh_token to get a new access_token before expiry."""
    global _tokens
    if not _tokens or not _tokens.refresh_token:
        raise ValueError("no_refresh_token_available")
    payload = {
        "grant_type": "refresh_token",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "refresh_token": _tokens.refresh_token,
    }
    async with httpx.AsyncClient(verify=verify_ssl, timeout=15.0) as http:
        r = await http.post(TOKEN_URL, json=payload)
        if r.status_code != 200:
            log.error("oauth_refresh_failed", status=r.status_code, body=r.text[:200])
            raise ValueError(f"refresh_failed: {r.status_code}")
        data = r.json()

    _tokens.access_token = data["access_token"]
    _tokens.refresh_token = data.get("refresh_token", _tokens.refresh_token)
    _tokens.expires_at = time.time() + int(data.get("expires_in", 3600))
    _save_tokens_to_disk()
    log.info("oauth_tokens_refreshed", cloud_id=_tokens.cloud_id)
    return _tokens


async def ensure_fresh_tokens(cfg: JiraOAuthConfig, *, verify_ssl: bool = True) -> JiraOAuthTokens | None:
    """Return current tokens, refreshing if expired. None if not connected."""
    if not _tokens:
        return None
    if _tokens.is_expired:
        try:
            return await refresh_tokens(cfg, verify_ssl=verify_ssl)
        except Exception as e:
            log.warning("oauth_refresh_failed_clearing", error=str(e)[:120])
            return None
    return _tokens


def disconnect() -> None:
    """Clear tokens (user-initiated disconnect)."""
    global _tokens
    _tokens = None
    _delete_tokens_from_disk()
    log.info("oauth_disconnected")
