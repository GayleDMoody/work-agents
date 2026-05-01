"""
Local-clone repo integration.

Pairs nicely with src/integrations/github_rest.py — the user can either pick a
remote GitHub repo (we'll fetch tree + files via API) OR a folder under a
configured root that already contains git clones (we'll read from disk).

Local-disk is preferred for big private repos since:
  - No API rate limits or fetch latency
  - Full file access (no 8KB-per-file cap when bundling context)
  - Branch / commit happen via plain git CLI; push uses the GitHub OAuth token
  - Diffs against the working tree are trivial
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.observability.logging import get_logger

log = get_logger("local_repo")

# Files / dirs we never include when building the context bundle
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
             ".next", ".turbo", "dist", "build", "target", "out", ".idea", ".vscode"}
SKIP_SUFFIXES = {".pyc", ".lock", ".log", ".min.js", ".map", ".pack",
                 ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg",
                 ".woff", ".woff2", ".ttf", ".eot",
                 ".zip", ".gz", ".tgz", ".tar"}
MAX_TREE_ENTRIES = 800
MAX_FILE_BYTES = 64 * 1024     # don't read files bigger than this for context
MAX_BUNDLE_FILES = 16          # cap files bundled as `relevant_files`


@dataclass
class LocalRepoSummary:
    name: str          # folder basename
    path: str          # absolute path
    has_git: bool
    branch: str = ""
    remote: str = ""   # parsed from `git remote get-url origin` if present
    last_commit: str = ""


@dataclass
class LocalRepoContext:
    name: str
    path: str
    branch: str
    remote: str
    file_tree: list[str] = field(default_factory=list)
    relevant_files: dict[str, str] = field(default_factory=dict)
    readme: str = ""
    stack_hints: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def list_local_repos(root: str) -> list[LocalRepoSummary]:
    """Return every git repo (immediate subfolder containing .git) under `root`."""
    root_p = Path(root).expanduser()
    if not root_p.exists() or not root_p.is_dir():
        return []
    out: list[LocalRepoSummary] = []
    for child in sorted(root_p.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        git_dir = child / ".git"
        has_git = git_dir.exists()
        if not has_git:
            continue
        s = LocalRepoSummary(name=child.name, path=str(child), has_git=True)
        # Branch + remote — best-effort
        try:
            s.branch = _git(child, "rev-parse", "--abbrev-ref", "HEAD") or ""
            s.remote = _git(child, "remote", "get-url", "origin") or ""
            s.last_commit = _git(child, "log", "-1", "--pretty=format:%h %s") or ""
        except Exception:
            pass
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Context bundling
# ---------------------------------------------------------------------------

def build_repo_context(repo_path: str, *, hints: list[str] | None = None) -> LocalRepoContext:
    """Read a slice of the local repo into a payload agents can reason about."""
    p = Path(repo_path).expanduser()
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"repo path not found: {repo_path}")

    branch = _git(p, "rev-parse", "--abbrev-ref", "HEAD") or ""
    remote = _git(p, "remote", "get-url", "origin") or ""

    # File tree (capped) — relative paths, skipping ignored dirs/suffixes
    tree: list[str] = []
    for dirpath, dirnames, filenames in os.walk(p):
        # in-place mutate to skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(p)
        for fname in filenames:
            if any(fname.endswith(suf) for suf in SKIP_SUFFIXES):
                continue
            rel = (rel_dir / fname).as_posix() if str(rel_dir) != "." else fname
            tree.append(rel)
            if len(tree) >= MAX_TREE_ENTRIES:
                break
        if len(tree) >= MAX_TREE_ENTRIES:
            break

    # README
    readme_text = ""
    for cand in ("README.md", "README.MD", "README.rst", "README"):
        rp = p / cand
        if rp.exists() and rp.stat().st_size < MAX_FILE_BYTES:
            try:
                readme_text = rp.read_text("utf-8", errors="replace")[:6000]
                break
            except Exception:
                pass

    # Stack hints
    stack_hints = [c for c in ("package.json", "pyproject.toml", "requirements.txt",
                               "Cargo.toml", "go.mod", "pom.xml", "build.gradle")
                   if (p / c).exists()]

    # Pick relevant files based on hints
    relevant_files: dict[str, str] = {}
    if hints:
        lows = [(rel, rel.lower()) for rel in tree]
        chosen: list[str] = []
        for h in hints:
            hl = (h or "").strip().lower()
            if not hl:
                continue
            for rel, rel_low in lows:
                if hl in rel_low and rel not in chosen and len(chosen) < MAX_BUNDLE_FILES:
                    chosen.append(rel)
        for rel in chosen:
            try:
                fp = p / rel
                if fp.exists() and fp.stat().st_size < MAX_FILE_BYTES:
                    relevant_files[rel] = fp.read_text("utf-8", errors="replace")[:8000]
            except Exception as e:
                log.warning("local_repo_read_failed", path=rel, error=str(e)[:120])

    return LocalRepoContext(
        name=p.name,
        path=str(p),
        branch=branch,
        remote=remote,
        file_tree=tree,
        relevant_files=relevant_files,
        readme=readme_text,
        stack_hints=stack_hints,
    )


# ---------------------------------------------------------------------------
# Apply changes + commit + push (Tier C end-to-end on disk)
# ---------------------------------------------------------------------------

@dataclass
class ApplyResult:
    branch: str
    commit_sha: str
    files_changed: list[str]
    pushed: bool
    error: str = ""


def apply_files_to_local(
    repo_path: str, *,
    files: list[dict[str, Any]],
    branch: str,
    commit_message: str,
    base_branch: str = "",
    push: bool = True,
    github_token: str = "",
) -> ApplyResult:
    """
    Write each `files[]` entry into the repo, then create a branch + commit
    the changes, optionally pushing to origin.

    Each entry: {path, action: 'create'|'modify'|'delete', content}
    """
    p = Path(repo_path).expanduser()
    if not p.exists():
        return ApplyResult(branch="", commit_sha="", files_changed=[], pushed=False, error="repo_not_found")

    # Resolve the base — checkout it first so the new branch starts from a known good commit
    if not base_branch:
        base_branch = _git(p, "rev-parse", "--abbrev-ref", "HEAD") or "main"

    # Stash any local uncommitted changes so we don't disturb the user's work
    has_changes = bool(_git(p, "status", "--porcelain"))
    stash_label = ""
    if has_changes:
        stash_label = f"work-agents-stash-{branch}"
        _git(p, "stash", "push", "-u", "-m", stash_label)

    try:
        # Make sure base is checked out + up to date
        _git(p, "checkout", base_branch)
        # Create or reset the work branch (checkout -B = create or reset)
        _git(p, "checkout", "-B", branch)

        # Apply each file
        changed: list[str] = []
        for f in files:
            rel = (f.get("path") or "").lstrip("/")
            if not rel:
                continue
            action = f.get("action", "create")
            target = p / rel
            if action == "delete":
                if target.exists():
                    target.unlink()
                    changed.append(rel)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f.get("content") or "", encoding="utf-8")
                changed.append(rel)

        if not changed:
            return ApplyResult(branch=branch, commit_sha="", files_changed=[], pushed=False, error="no_changes")

        # Stage + commit
        _git(p, "add", "-A")
        # If nothing actually changed (e.g. agents wrote identical content), `commit` will fail with code 1.
        try:
            _git(p, "-c", "user.email=agents@work-agents.local",
                    "-c", "user.name=Work Agents",
                    "commit", "-m", commit_message)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode("utf-8", errors="replace")
            if "nothing to commit" in stderr.lower():
                return ApplyResult(branch=branch, commit_sha="", files_changed=changed, pushed=False, error="no_diff_after_apply")
            raise

        commit_sha = _git(p, "rev-parse", "HEAD") or ""

        pushed = False
        if push:
            # Push using OAuth token if provided. Insert it into the remote URL
            # for this push only — we don't persist a credential helper.
            remote_url = _git(p, "remote", "get-url", "origin") or ""
            if github_token and remote_url.startswith("https://"):
                # Format: https://x-access-token:TOKEN@github.com/owner/repo.git
                authed_url = remote_url.replace(
                    "https://",
                    f"https://x-access-token:{github_token}@",
                    1,
                )
                _git(p, "push", "-u", authed_url, branch, "--force-with-lease")
            else:
                _git(p, "push", "-u", "origin", branch, "--force-with-lease")
            pushed = True

        # Restore the user's local state: switch back to base branch + un-stash.
        _git(p, "checkout", base_branch)
        if stash_label:
            try:
                # Find the stash by message
                stash_list = _git(p, "stash", "list") or ""
                for line in stash_list.splitlines():
                    if stash_label in line:
                        ref = line.split(":", 1)[0].strip()
                        _git(p, "stash", "pop", ref)
                        break
            except Exception as e:
                log.warning("stash_pop_failed", error=str(e)[:120])

        return ApplyResult(branch=branch, commit_sha=commit_sha, files_changed=changed, pushed=pushed)
    except Exception as e:
        log.exception("apply_local_failed")
        return ApplyResult(branch=branch, commit_sha="", files_changed=[], pushed=False, error=str(e)[:200])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub remote URL. Returns None if not GitHub."""
    if not remote_url:
        return None
    s = remote_url.strip()
    # SSH form: git@github.com:owner/repo.git
    if s.startswith("git@github.com:"):
        body = s.split(":", 1)[1]
    elif "github.com/" in s:
        body = s.split("github.com/", 1)[1]
    else:
        return None
    body = body.rstrip("/")
    if body.endswith(".git"):
        body = body[:-4]
    parts = body.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def _git(cwd: Path, *args: str) -> str:
    """Run `git` in `cwd` and return stdout (stripped). Raises on non-zero exit."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
        )
        return (r.stdout or b"").decode("utf-8", errors="replace").strip()
    except subprocess.CalledProcessError:
        raise
    except FileNotFoundError:
        raise RuntimeError("git is not installed or not in PATH")
