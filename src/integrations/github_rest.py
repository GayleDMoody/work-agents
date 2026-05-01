"""
Pure-REST GitHub client used by the Tier-C "agents work on actual code" flow.

Why a new module:
    The existing src/integrations/git_client.py wraps GitPython (local clones)
    + PyGithub. For the agent pipeline we don't actually need a local clone —
    every operation we care about (read tree, read file, create branch, write
    file, open PR) is a single REST call. Avoiding the local clone:
      - Eliminates "git clone failed behind corp proxy" failure modes
      - Skips slow disk IO on first-touch repos
      - Plays cleanly with the OAuth Bearer token we already have
      - Simplifies the code viewer's diff (compare original blob vs agent output)

All methods are async (httpx) and accept the OAuth access token directly.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from src.observability.logging import get_logger

log = get_logger("github_rest")

API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


@dataclass
class RepoFile:
    path: str
    sha: str
    size: int
    type: str  # "blob" | "tree"


@dataclass
class RepoSummary:
    """Subset of GitHub repo metadata the dashboard cares about."""
    full_name: str          # "owner/repo"
    description: str
    default_branch: str
    private: bool
    updated_at: str
    language: str = ""
    stargazers_count: int = 0


# ---------------------------------------------------------------------------
# Listing / reading
# ---------------------------------------------------------------------------

async def list_user_repos(token: str, per_page: int = 50) -> list[RepoSummary]:
    """Repos accessible by the authenticated user, sorted by recent activity."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.get(
            f"{API}/user/repos",
            headers=_headers(token),
            params={"sort": "updated", "per_page": per_page, "affiliation": "owner,collaborator,organization_member"},
        )
        r.raise_for_status()
        out: list[RepoSummary] = []
        for repo in r.json():
            out.append(RepoSummary(
                full_name=repo.get("full_name", ""),
                description=repo.get("description") or "",
                default_branch=repo.get("default_branch") or "main",
                private=bool(repo.get("private")),
                updated_at=repo.get("updated_at", ""),
                language=repo.get("language") or "",
                stargazers_count=repo.get("stargazers_count", 0),
            ))
        return out


async def get_repo(token: str, full_name: str) -> dict[str, Any]:
    """Full repo metadata (used to look up default branch + head sha)."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.get(f"{API}/repos/{full_name}", headers=_headers(token))
        r.raise_for_status()
        return r.json()


async def list_repo_tree(token: str, full_name: str, branch: str, *, recursive: bool = True) -> list[RepoFile]:
    """Flat list of every file in the repo at the given branch."""
    # Resolve branch -> tree sha
    async with httpx.AsyncClient(timeout=20.0) as http:
        b = await http.get(f"{API}/repos/{full_name}/branches/{branch}", headers=_headers(token))
        b.raise_for_status()
        tree_sha = b.json()["commit"]["commit"]["tree"]["sha"]

        params = {"recursive": "1"} if recursive else {}
        t = await http.get(f"{API}/repos/{full_name}/git/trees/{tree_sha}", headers=_headers(token), params=params)
        t.raise_for_status()
        body = t.json()
        files: list[RepoFile] = []
        for entry in body.get("tree", []):
            files.append(RepoFile(
                path=entry.get("path", ""),
                sha=entry.get("sha", ""),
                size=int(entry.get("size") or 0),
                type=entry.get("type", "blob"),
            ))
        if body.get("truncated"):
            log.warning("repo_tree_truncated", repo=full_name, branch=branch, count=len(files))
        return files


async def read_file(token: str, full_name: str, path: str, *, ref: str | None = None) -> dict[str, Any]:
    """Return {content: str, sha: str, size: int, encoding: str}.

    GitHub's contents API base64-encodes blobs; we decode to UTF-8 text. Returns
    {"missing": True} if the file doesn't exist (404)."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        params = {"ref": ref} if ref else {}
        r = await http.get(
            f"{API}/repos/{full_name}/contents/{path}",
            headers=_headers(token),
            params=params,
        )
        if r.status_code == 404:
            return {"missing": True, "path": path}
        r.raise_for_status()
        body = r.json()
        if isinstance(body, list):
            # It's a directory listing; return summary
            return {"is_dir": True, "path": path, "entries": [e.get("name") for e in body]}
        encoding = body.get("encoding")
        raw = body.get("content") or ""
        if encoding == "base64":
            try:
                text = base64.b64decode(raw).decode("utf-8", errors="replace")
            except Exception:
                text = ""
        else:
            text = raw
        return {
            "content": text,
            "sha": body.get("sha", ""),
            "size": int(body.get("size") or 0),
            "encoding": encoding or "",
            "path": path,
        }


# ---------------------------------------------------------------------------
# Writing — branch + file PUTs + PR
# ---------------------------------------------------------------------------

async def create_branch(token: str, full_name: str, *, new_branch: str, from_branch: str) -> dict[str, Any]:
    """Create `new_branch` at the same commit as `from_branch`."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        b = await http.get(f"{API}/repos/{full_name}/branches/{from_branch}", headers=_headers(token))
        b.raise_for_status()
        sha = b.json()["commit"]["sha"]

        # Try to create the ref. If it already exists, fetch and return it.
        r = await http.post(
            f"{API}/repos/{full_name}/git/refs",
            headers=_headers(token),
            json={"ref": f"refs/heads/{new_branch}", "sha": sha},
        )
        if r.status_code == 422 and "Reference already exists" in r.text:
            existing = await http.get(f"{API}/repos/{full_name}/branches/{new_branch}", headers=_headers(token))
            existing.raise_for_status()
            return {"created": False, "branch": new_branch, "sha": existing.json()["commit"]["sha"]}
        r.raise_for_status()
        return {"created": True, "branch": new_branch, "sha": sha}


async def put_file(
    token: str, full_name: str, *, path: str, content: str, branch: str,
    message: str, existing_sha: str | None = None,
) -> dict[str, Any]:
    """Create or update `path` on `branch`. Pass `existing_sha` to update; omit to create."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    payload: dict[str, Any] = {"message": message, "content": encoded, "branch": branch}
    if existing_sha:
        payload["sha"] = existing_sha
    async with httpx.AsyncClient(timeout=20.0) as http:
        r = await http.put(
            f"{API}/repos/{full_name}/contents/{path}",
            headers=_headers(token),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


async def delete_file(
    token: str, full_name: str, *, path: str, branch: str, message: str, existing_sha: str,
) -> dict[str, Any]:
    payload = {"message": message, "branch": branch, "sha": existing_sha}
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.request(
            "DELETE", f"{API}/repos/{full_name}/contents/{path}",
            headers=_headers(token), json=payload,
        )
        r.raise_for_status()
        return r.json()


async def open_pull_request(
    token: str, full_name: str, *, title: str, body: str, head: str, base: str, draft: bool = True,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as http:
        r = await http.post(
            f"{API}/repos/{full_name}/pulls",
            headers=_headers(token),
            json={"title": title, "body": body, "head": head, "base": base, "draft": draft},
        )
        if r.status_code == 422 and "A pull request already exists" in r.text:
            # Find the existing PR
            existing = await http.get(
                f"{API}/repos/{full_name}/pulls",
                headers=_headers(token),
                params={"head": f"{full_name.split('/')[0]}:{head}", "state": "open"},
            )
            existing.raise_for_status()
            prs = existing.json()
            if prs:
                return prs[0]
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Convenience: bundle a context payload for agents
# ---------------------------------------------------------------------------

@dataclass
class RepoContext:
    """Context bundle the agent pipeline gets at kickoff so it can reason about
    real code instead of writing in a vacuum."""
    full_name: str
    default_branch: str
    description: str
    file_tree: list[str]                    # list of paths, capped to a sensible size
    relevant_files: dict[str, str] = field(default_factory=dict)  # path -> content (capped)
    readme: str = ""
    stack_hints: list[str] = field(default_factory=list)


async def build_repo_context(
    token: str, full_name: str, *, hints: list[str] | None = None, max_files: int = 12,
) -> RepoContext:
    """Pull a compact representation of the repo for agent prompts.

    `hints` are search strings (typically pulled from the Jira ticket text) used to
    pick which files to include verbatim — e.g. ['MonitoringResults', 'BatchSummary']
    will pull files whose paths contain any of those substrings.
    """
    repo = await get_repo(token, full_name)
    branch = repo.get("default_branch") or "main"

    tree = await list_repo_tree(token, full_name, branch)
    paths = [f.path for f in tree if f.type == "blob"]

    # README
    readme_text = ""
    for candidate in ("README.md", "README.MD", "README.rst", "README"):
        if candidate in paths:
            res = await read_file(token, full_name, candidate, ref=branch)
            if res.get("content"):
                readme_text = (res["content"] or "")[:6000]
            break

    # Stack hints — peek at canonical project files
    stack_hints: list[str] = []
    for canonical in ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml"):
        if canonical in paths:
            stack_hints.append(canonical)

    # Pick relevant files: any path matching any hint substring (case-insensitive).
    # Cap total to keep agent context payload manageable.
    relevant_files: dict[str, str] = {}
    if hints:
        lower_paths = [(p, p.lower()) for p in paths]
        chosen: list[str] = []
        for h in hints:
            hl = h.lower()
            for p, pl in lower_paths:
                if hl in pl and p not in chosen and len(chosen) < max_files:
                    chosen.append(p)
        for p in chosen:
            try:
                res = await read_file(token, full_name, p, ref=branch)
                if res.get("content"):
                    # Trim individual files so the bundle stays small
                    relevant_files[p] = (res["content"] or "")[:8000]
            except Exception as e:
                log.warning("repo_file_read_failed", path=p, error=str(e)[:100])

    return RepoContext(
        full_name=full_name,
        default_branch=branch,
        description=repo.get("description") or "",
        # Cap file tree rendering to ~300 entries so prompt stays sane
        file_tree=paths[:300],
        relevant_files=relevant_files,
        readme=readme_text,
        stack_hints=stack_hints,
    )
