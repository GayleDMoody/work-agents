"""Git client combining GitPython (local) with PyGithub (remote)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from src.observability.logging import get_logger

log = get_logger("git_client")


class GitClient:
    """Manages Git operations via GitPython + PyGithub."""

    def __init__(self, repo_path: str, github_token: str, github_repo_name: str):
        self.repo_path = repo_path
        self.github_token = github_token
        self.github_repo_name = github_repo_name
        self._repo = None
        self._github = None
        self._gh_repo = None

    def _get_repo(self):
        if self._repo is None:
            import git
            self._repo = git.Repo(self.repo_path)
        return self._repo

    def _get_gh_repo(self):
        if self._gh_repo is None:
            from github import Github
            self._github = Github(self.github_token)
            self._gh_repo = self._github.get_repo(self.github_repo_name)
        return self._gh_repo

    async def create_branch(self, branch_name: str, from_branch: str = "main") -> str:
        """Create and checkout a new branch."""
        def _create():
            repo = self._get_repo()
            origin = repo.remotes.origin
            origin.fetch()
            base = repo.refs[f"origin/{from_branch}"]
            new_branch = repo.create_head(branch_name, base)
            new_branch.checkout()
            return branch_name

        result = await asyncio.to_thread(_create)
        log.info("branch_created", branch=branch_name, from_branch=from_branch)
        return result

    async def write_file(self, file_path: str, content: str) -> None:
        """Write content to a file in the repo."""
        def _write():
            full_path = Path(self.repo_path) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        await asyncio.to_thread(_write)

    async def read_file(self, file_path: str) -> str:
        """Read file content from repo."""
        def _read():
            full_path = Path(self.repo_path) / file_path
            return full_path.read_text()

        return await asyncio.to_thread(_read)

    async def list_files(self, directory: str = "", pattern: str = "*") -> list[str]:
        """List files matching pattern."""
        def _list():
            base = Path(self.repo_path) / directory
            return [str(p.relative_to(self.repo_path)) for p in base.rglob(pattern) if p.is_file()]

        return await asyncio.to_thread(_list)

    async def commit(self, message: str, files: list[str]) -> str:
        """Stage specific files and commit."""
        def _commit():
            repo = self._get_repo()
            repo.index.add(files)
            commit = repo.index.commit(message)
            return str(commit.hexsha)

        sha = await asyncio.to_thread(_commit)
        log.info("committed", sha=sha[:8], files=len(files))
        return sha

    async def push(self, branch_name: str) -> None:
        """Push branch to origin."""
        def _push():
            repo = self._get_repo()
            origin = repo.remotes.origin
            origin.push(branch_name)

        await asyncio.to_thread(_push)
        log.info("pushed", branch=branch_name)

    async def create_pr(
        self, title: str, body: str, base: str = "main", head: str | None = None
    ) -> int:
        """Create a pull request. Returns PR number."""
        def _create():
            gh_repo = self._get_gh_repo()
            pr = gh_repo.create_pull(
                title=title,
                body=body,
                base=base,
                head=head or self._get_repo().active_branch.name,
            )
            return pr.number

        pr_number = await asyncio.to_thread(_create)
        log.info("pr_created", pr_number=pr_number, title=title)
        return pr_number

    async def add_pr_review_comment(
        self,
        pr_number: int,
        body: str,
        file_path: str | None = None,
        line: int | None = None,
    ) -> None:
        """Add a review comment to a PR."""
        def _comment():
            gh_repo = self._get_gh_repo()
            pr = gh_repo.get_pull(pr_number)
            if file_path and line:
                commit = pr.get_commits().reversed[0]
                pr.create_review_comment(
                    body=body,
                    commit=commit,
                    path=file_path,
                    line=line,
                )
            else:
                pr.create_issue_comment(body)

        await asyncio.to_thread(_comment)

    async def get_diff(self, base: str = "main") -> str:
        """Get diff between current branch and base."""
        def _diff():
            repo = self._get_repo()
            return repo.git.diff(f"origin/{base}")

        return await asyncio.to_thread(_diff)

    async def get_file_tree(self, directory: str = "") -> list[str]:
        """Get recursive file listing."""
        return await self.list_files(directory)

    async def merge_pr(self, pr_number: int, merge_method: str = "squash") -> bool:
        """Merge a pull request."""
        def _merge():
            gh_repo = self._get_gh_repo()
            pr = gh_repo.get_pull(pr_number)
            result = pr.merge(merge_method=merge_method)
            return result.merged

        merged = await asyncio.to_thread(_merge)
        log.info("pr_merged", pr_number=pr_number, merged=merged)
        return merged
