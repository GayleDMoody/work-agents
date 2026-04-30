"""Jira API client wrapper."""

from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncGenerator, Optional

from src.observability.logging import get_logger

log = get_logger("jira_client")


class JiraClient:
    """Async wrapper around the jira Python library.

    Supports two auth modes:
        1. Basic auth (email + API token) — works only on Atlassian Cloud sites
           that don't enforce SSO. Pass server_url + email + api_token.
        2. OAuth 2.0 (3LO) Bearer auth — required for SSO-enforced sites.
           Pass oauth_token + cloud_id; the client routes calls through
           https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/...
    """

    def __init__(
        self,
        server_url: str = "",
        email: str = "",
        api_token: str = "",
        *,
        verify_ssl: bool = True,
        ca_bundle: str | None = None,
        oauth_token: str | None = None,
        cloud_id: str | None = None,
    ):
        """
        Args:
            server_url: e.g. https://yourorg.atlassian.net
            email: account email tied to the API token
            api_token: token from id.atlassian.com/manage-profile/security/api-tokens
            verify_ssl: when False, skip TLS cert verification. Use only on
                corporate networks doing TLS interception (Palo Alto, ZScaler, etc.)
                where you trust the network. Default True.
            ca_bundle: optional path to a custom CA bundle (preferred over
                disabling verification on corp networks). When set, takes
                precedence over verify_ssl=False.
        """
        self.server_url = server_url
        self.email = email
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        self.ca_bundle = ca_bundle
        self.oauth_token = oauth_token
        self.cloud_id = cloud_id
        self._jira = None

        if oauth_token and not cloud_id:
            raise ValueError("OAuth mode requires both oauth_token and cloud_id")
        if not oauth_token and not (server_url and email and api_token):
            raise ValueError("Basic auth mode requires server_url + email + api_token")

    @property
    def is_oauth(self) -> bool:
        return self.oauth_token is not None

    def _get_client(self):
        if self._jira is None:
            from jira import JIRA
            verify: bool | str = self.ca_bundle or self.verify_ssl

            if self.is_oauth:
                # OAuth: route through api.atlassian.com/ex/jira/{cloud_id}
                # using a Bearer token. The jira lib accepts a custom Session
                # via the get_server_info=False trick + a session with auth header.
                import requests
                session = requests.Session()
                session.headers.update({
                    "Authorization": f"Bearer {self.oauth_token}",
                    "Accept": "application/json",
                })
                session.verify = verify
                base = f"https://api.atlassian.com/ex/jira/{self.cloud_id}"
                # Pass an empty basic_auth to bypass the lib's auth setup; the
                # session's Authorization header carries the real auth.
                options = {"server": base, "verify": verify, "rest_api_version": "3"}
                self._jira = JIRA(options=options, get_server_info=False)
                # Replace the auto-created session so our Bearer header sticks
                self._jira._session = session
            else:
                # Basic auth (email + API token), direct site URL
                options = {"server": self.server_url, "verify": verify}
                self._jira = JIRA(options=options, basic_auth=(self.email, self.api_token))

            if not self.verify_ssl and not self.ca_bundle:
                log.warning("jira_ssl_verification_disabled",
                            mode="oauth" if self.is_oauth else "basic",
                            note="trust_only_on_corporate_intercepting_proxies")
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                except Exception:
                    pass
        return self._jira

    async def fetch_ticket(self, ticket_key: str) -> dict[str, Any]:
        """Fetch full ticket details and return as a dict."""
        def _fetch():
            jira = self._get_client()
            issue = jira.issue(ticket_key)
            fields = issue.fields

            # Extract acceptance criteria from description
            desc = fields.description or ""
            ac = []
            in_ac = False
            for line in desc.split("\n"):
                if "acceptance criteria" in line.lower():
                    in_ac = True
                    continue
                if in_ac and line.strip().startswith(("-", "*", "[")):
                    ac.append(line.strip().lstrip("-*[] "))
                elif in_ac and line.strip() == "":
                    in_ac = False

            return {
                "key": ticket_key,
                "summary": fields.summary or "",
                "description": desc,
                "issue_type": fields.issuetype.name if fields.issuetype else "story",
                "priority": fields.priority.name if fields.priority else "medium",
                "labels": fields.labels or [],
                "components": [c.name for c in (fields.components or [])],
                "acceptance_criteria": ac,
                "linked_issues": [
                    link.outwardIssue.key if hasattr(link, "outwardIssue") and link.outwardIssue
                    else link.inwardIssue.key if hasattr(link, "inwardIssue") and link.inwardIssue
                    else ""
                    for link in (fields.issuelinks or [])
                ],
                "comments": [
                    {"author": c.author.displayName, "body": c.body, "created": c.created}
                    for c in (fields.comment.comments if hasattr(fields, "comment") and fields.comment else [])
                ],
                "attachments": [
                    {"filename": a.filename, "url": a.content}
                    for a in (fields.attachment or [])
                ],
                "reporter": fields.reporter.displayName if fields.reporter else "",
                "assignee": fields.assignee.displayName if fields.assignee else None,
                "story_points": getattr(fields, "customfield_10016", None),
                "raw_data": {"key": ticket_key},
            }

        return await asyncio.to_thread(_fetch)

    async def add_comment(self, ticket_key: str, body: str) -> None:
        """Post a comment on a ticket."""
        def _comment():
            jira = self._get_client()
            jira.add_comment(ticket_key, body)

        await asyncio.to_thread(_comment)
        log.info("comment_added", ticket_key=ticket_key)

    async def transition_ticket(self, ticket_key: str, status_name: str) -> None:
        """Move ticket to a new status."""
        def _transition():
            jira = self._get_client()
            transitions = jira.transitions(ticket_key)
            for t in transitions:
                if t["name"].lower() == status_name.lower():
                    jira.transition_issue(ticket_key, t["id"])
                    return
            raise ValueError(f"Transition '{status_name}' not found for {ticket_key}")

        await asyncio.to_thread(_transition)
        log.info("ticket_transitioned", ticket_key=ticket_key, status=status_name)

    async def update_fields(self, ticket_key: str, fields: dict[str, Any]) -> None:
        """Update arbitrary fields on a ticket."""
        def _update():
            jira = self._get_client()
            issue = jira.issue(ticket_key)
            issue.update(fields=fields)

        await asyncio.to_thread(_update)

    async def get_transitions(self, ticket_key: str) -> list[dict[str, Any]]:
        """Get available transitions for a ticket."""
        def _get():
            jira = self._get_client()
            return jira.transitions(ticket_key)

        return await asyncio.to_thread(_get)

    async def search_tickets(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Search tickets with JQL."""
        def _search():
            jira = self._get_client()
            issues = jira.search_issues(jql, maxResults=max_results)
            return [
                {"key": i.key, "summary": i.fields.summary, "status": i.fields.status.name}
                for i in issues
            ]

        return await asyncio.to_thread(_search)

    async def wait_for_comment_matching(
        self, ticket_key: str, pattern: str, timeout_seconds: int = 86400, poll_interval: int = 60
    ) -> str | None:
        """Poll for a comment matching a regex pattern. Used for human-in-the-loop."""
        import time
        start = time.time()
        compiled = re.compile(pattern, re.IGNORECASE)
        seen_comments: set[str] = set()

        while time.time() - start < timeout_seconds:
            def _check():
                jira = self._get_client()
                issue = jira.issue(ticket_key)
                for comment in issue.fields.comment.comments:
                    if comment.id not in seen_comments:
                        seen_comments.add(comment.id)
                        if compiled.search(comment.body):
                            return comment.body
                return None

            result = await asyncio.to_thread(_check)
            if result:
                return result

            await asyncio.sleep(poll_interval)

        return None
