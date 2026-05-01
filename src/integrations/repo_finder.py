"""
Repo + PR discovery for the Investigator phase.

When a pipeline is triggered without an explicit repo selection, we run this
discovery step first so agents start with grounded knowledge of:
  - Which repos in the user's local clone or GitHub workspace are likely
    relevant to the ticket
  - Whether anyone (human or prior agent run) has already opened a PR for
    this ticket and what state it's in

Two parallel searches:
  - LOCAL  — git log / branch enumeration / file-content grep across every
             clone under the configured root
  - GITHUB — GitHub Search API for issues / PRs whose body or title mentions
             the ticket key
"""
from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from src.observability.logging import get_logger

log = get_logger("repo_finder")


@dataclass
class LocalEvidence:
    repo_name: str
    repo_path: str
    remote: str = ""             # GitHub remote URL if any
    branches: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)   # short SHA + subject
    files_with_mentions: list[str] = field(default_factory=list)
    score: int = 0               # higher = more confident match


@dataclass
class GitHubPR:
    number: int
    repo_full_name: str          # "owner/repo"
    title: str
    body: str
    state: str                   # open | closed
    merged: bool
    draft: bool
    author: str
    head_branch: str
    base_branch: str
    html_url: str
    created_at: str
    updated_at: str
    comments: int
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0
    files_summary: list[str] = field(default_factory=list)
    diff_excerpt: str = ""       # first ~6KB of the unified diff


@dataclass
class Dossier:
    ticket_key: str
    local_evidence: list[LocalEvidence] = field(default_factory=list)
    open_prs: list[GitHubPR] = field(default_factory=list)
    other_prs: list[GitHubPR] = field(default_factory=list)   # closed/merged
    recommended_repo_local: str = ""    # path to local clone (best guess)
    recommended_repo_github: str = ""   # owner/repo full name (best guess)


# ---------------------------------------------------------------------------
# Local-clone search
# ---------------------------------------------------------------------------

LOCAL_GREP_MAX_FILES = 20      # cap per repo to stay quick
LOCAL_LOG_LIMIT = 200          # commits inspected per repo


def _git(cwd: Path, *args: str, timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd),
            check=False, capture_output=True, timeout=timeout,
        )
        return (r.stdout or b"").decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def search_local_repos(root: str, ticket_key: str) -> list[LocalEvidence]:
    """Walk every git clone under `root` looking for ticket-key signals.

    Each repo gets scored on three signals (branches, commits, file mentions).
    We're optimising for fast wins on the demo's lifetime, so per-repo work is
    bounded (cap on log lines, cap on grep results)."""
    root_p = Path(root).expanduser()
    if not root_p.exists() or not root_p.is_dir():
        return []
    key_pat = re.compile(re.escape(ticket_key), re.IGNORECASE)

    results: list[LocalEvidence] = []
    for child in sorted(root_p.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or not (child / ".git").exists():
            continue

        ev = LocalEvidence(repo_name=child.name, repo_path=str(child))
        ev.remote = _git(child, "remote", "get-url", "origin") or ""

        # Branch mentions (local + remote)
        branches_raw = _git(child, "branch", "--list", "-a") or ""
        for line in branches_raw.splitlines():
            cleaned = line.strip().lstrip("*").strip()
            if key_pat.search(cleaned) and cleaned not in ev.branches:
                ev.branches.append(cleaned)
                ev.score += 5  # branch match is a strong signal

        # Commit log mentions on the current branch
        log_raw = _git(child, "log", f"-{LOCAL_LOG_LIMIT}", "--pretty=format:%h %s")
        for line in log_raw.splitlines():
            if key_pat.search(line):
                ev.commits.append(line.strip())
                ev.score += 2
                if len(ev.commits) >= 10:
                    break

        # File-content grep — fast, capped, ignores common junk dirs
        try:
            grep = subprocess.run(
                ["git", "grep", "-l", "--ignore-case", ticket_key, "--",
                 ":!node_modules", ":!*.lock", ":!*.min.js", ":!dist"],
                cwd=str(child), check=False, capture_output=True, timeout=10.0,
            )
            for fp in (grep.stdout or b"").decode("utf-8", errors="replace").splitlines():
                fp = fp.strip()
                if fp:
                    ev.files_with_mentions.append(fp)
                    ev.score += 1
                if len(ev.files_with_mentions) >= LOCAL_GREP_MAX_FILES:
                    break
        except Exception:
            pass

        if ev.score > 0:
            results.append(ev)

    results.sort(key=lambda e: e.score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# GitHub PR search
# ---------------------------------------------------------------------------

def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def search_github_prs(
    token: str, ticket_key: str, *, per_page: int = 30,
) -> list[GitHubPR]:
    """Use the GitHub Search API to find PRs (open + closed) referencing the ticket."""
    if not token:
        return []
    out: list[GitHubPR] = []
    # GitHub's search treats hyphens as separators, so quote the key
    q = f'"{ticket_key}" in:title,body type:pr'
    async with httpx.AsyncClient(timeout=20.0) as http:
        try:
            r = await http.get(
                "https://api.github.com/search/issues",
                headers=_github_headers(token),
                params={"q": q, "sort": "updated", "order": "desc", "per_page": per_page},
            )
            r.raise_for_status()
            items = r.json().get("items", []) or []
        except Exception as e:
            log.warning("github_pr_search_failed", error=str(e)[:160])
            return []

        # Each search result is an issue object; we need the PR detail for diff stats
        for item in items[:per_page]:
            # Pull repo full_name from the html_url, since `repository_url` is the API URL
            html = item.get("html_url", "")
            m = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", html)
            if not m:
                continue
            full_name = m.group(1)
            number = int(m.group(2))
            # Fetch full PR detail (stats + branches)
            try:
                d = await http.get(
                    f"https://api.github.com/repos/{full_name}/pulls/{number}",
                    headers=_github_headers(token),
                )
                d.raise_for_status()
                pr = d.json()
            except Exception:
                pr = {}

            # Files summary — first 10
            files_summary: list[str] = []
            try:
                f = await http.get(
                    f"https://api.github.com/repos/{full_name}/pulls/{number}/files",
                    headers=_github_headers(token),
                    params={"per_page": 10},
                )
                if f.status_code == 200:
                    for fobj in f.json():
                        files_summary.append(
                            f"{fobj.get('status','?')[:6]:6} {fobj.get('filename','')[:80]} (+{fobj.get('additions',0)}/-{fobj.get('deletions',0)})"
                        )
            except Exception:
                pass

            # Diff (capped) — fetch via the .diff Accept header
            diff_text = ""
            try:
                dd = await http.get(
                    f"https://api.github.com/repos/{full_name}/pulls/{number}",
                    headers={**_github_headers(token), "Accept": "application/vnd.github.v3.diff"},
                )
                if dd.status_code == 200:
                    diff_text = (dd.text or "")[:6000]
            except Exception:
                pass

            out.append(GitHubPR(
                number=number,
                repo_full_name=full_name,
                title=item.get("title", "") or pr.get("title", ""),
                body=(item.get("body") or pr.get("body") or "")[:2000],
                state=item.get("state", "") or pr.get("state", ""),
                merged=bool(pr.get("merged")),
                draft=bool(pr.get("draft")),
                author=(item.get("user") or {}).get("login", ""),
                head_branch=((pr.get("head") or {}).get("ref")) or "",
                base_branch=((pr.get("base") or {}).get("ref")) or "",
                html_url=html,
                created_at=item.get("created_at", "") or pr.get("created_at", ""),
                updated_at=item.get("updated_at", "") or pr.get("updated_at", ""),
                comments=int(item.get("comments", 0) or 0),
                changed_files=int(pr.get("changed_files", 0) or 0),
                additions=int(pr.get("additions", 0) or 0),
                deletions=int(pr.get("deletions", 0) or 0),
                files_summary=files_summary,
                diff_excerpt=diff_text,
            ))
    return out


# ---------------------------------------------------------------------------
# Top-level dossier builder
# ---------------------------------------------------------------------------

async def build_dossier(
    ticket_key: str, *, local_root: str, github_token: str = "",
) -> Dossier:
    """Run both searches and pick the most likely target repo for the ticket."""
    # Run local search in a thread (it's CPU+IO bound, blocks otherwise)
    local_task = asyncio.create_task(asyncio.to_thread(search_local_repos, local_root, ticket_key))
    gh_task = asyncio.create_task(search_github_prs(github_token, ticket_key)) if github_token else None

    local = await local_task
    prs = await gh_task if gh_task else []

    open_prs = [p for p in prs if p.state == "open"]
    other_prs = [p for p in prs if p.state != "open"]

    # Recommendation: prefer a repo that BOTH appears in local evidence AND has an open PR.
    # If only one source agrees, take its top hit. If nothing matches, leave blank.
    rec_local = ""
    rec_github = ""
    if local:
        rec_local = local[0].repo_path
    if open_prs:
        rec_github = open_prs[0].repo_full_name
    # Cross-confirm: does the local top hit map to the GitHub top hit?
    if local and open_prs:
        from src.integrations.local_repo import parse_github_owner_repo
        for ev in local[:3]:
            gh = parse_github_owner_repo(ev.remote)
            if gh and f"{gh[0]}/{gh[1]}" == open_prs[0].repo_full_name:
                rec_local = ev.repo_path
                rec_github = open_prs[0].repo_full_name
                break

    return Dossier(
        ticket_key=ticket_key,
        local_evidence=local,
        open_prs=open_prs,
        other_prs=other_prs,
        recommended_repo_local=rec_local,
        recommended_repo_github=rec_github,
    )
