"""
The Investigator runs *before* the main agent pipeline when the user triggered
a ticket without explicitly picking a repo.

It:
    1. Pulls the Jira ticket details (re-uses _resolve_ticket from the engine).
    2. Searches local clones + GitHub PRs for ticket-key signals (repo_finder).
    3. Asks Claude to read the dossier and decide:
        - which repo(s) the work belongs in
        - whether an existing PR already covers the ticket sufficiently
        - if not, what additional work is required
    4. Returns a structured verdict the API layer uses to either short-circuit
       (sufficient PR found) or continue with the auto-picked repo.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.agents.claude_mixin import ClaudeMixin, _emit_agent_thought
from src.integrations.repo_finder import Dossier, GitHubPR, LocalEvidence, build_dossier
from src.observability.logging import get_logger

log = get_logger("investigator")

INVESTIGATOR_AGENT_ID = "investigator"


@dataclass
class InvestigatorVerdict:
    """Structured output Claude produces."""
    target_repos: list[str] = field(default_factory=list)
    """Recommended target repo(s). Each entry: 'owner/repo' or local path."""

    existing_pr_url: str = ""
    """URL of an existing PR that addresses the ticket, if any."""

    sufficient: bool = False
    """True iff the existing PR already addresses the full ticket scope and
    no additional agent work is needed."""

    reasoning: str = ""
    """Short justification (2–3 sentences) explaining the verdict."""

    additional_work: list[str] = field(default_factory=list)
    """If not sufficient, what specific items still need work."""

    confidence: str = "medium"      # low | medium | high


@dataclass
class InvestigationResult:
    dossier: Dossier
    verdict: InvestigatorVerdict
    raw_claude_output: str = ""

    def to_artifact(self) -> dict[str, Any]:
        """Render as an artifact dict the dashboard's ArtifactViewer can render."""
        # Pretty-print the dossier so it's readable in the JSON pane
        d = self.dossier
        json_dict = {
            "verdict": asdict(self.verdict),
            "ticket_key": d.ticket_key,
            "recommended_repo_local": d.recommended_repo_local,
            "recommended_repo_github": d.recommended_repo_github,
            "local_evidence": [
                {
                    "repo_name": ev.repo_name,
                    "repo_path": ev.repo_path,
                    "remote": ev.remote,
                    "score": ev.score,
                    "branches": ev.branches,
                    "commits": ev.commits[:5],
                    "files_with_mentions_count": len(ev.files_with_mentions),
                    "files_sample": ev.files_with_mentions[:5],
                }
                for ev in d.local_evidence[:10]
            ],
            "open_prs": [_pr_summary(p) for p in d.open_prs],
            "other_prs": [_pr_summary(p) for p in d.other_prs[:5]],
        }
        # Build a human-readable summary for the artifact's "raw" pane.
        raw = _format_dossier_text(d, self.verdict)
        return {
            "id": f"{INVESTIGATOR_AGENT_ID}-{d.ticket_key}",
            "artifact_type": "investigation",
            "name": f"Investigator dossier for {d.ticket_key}",
            "agent_id": INVESTIGATOR_AGENT_ID,
            "phase": "intake",
            "raw": raw,
            "json_dict": json_dict,
            "files": [],
            "summary": self.verdict.reasoning or "Investigation complete",
        }


def _pr_summary(p: GitHubPR) -> dict[str, Any]:
    return {
        "number": p.number,
        "repo": p.repo_full_name,
        "title": p.title,
        "state": p.state,
        "merged": p.merged,
        "draft": p.draft,
        "author": p.author,
        "head": p.head_branch,
        "base": p.base_branch,
        "url": p.html_url,
        "comments": p.comments,
        "changed_files": p.changed_files,
        "additions": p.additions,
        "deletions": p.deletions,
        "files_sample": p.files_summary[:5],
    }


def _format_dossier_text(d: Dossier, v: InvestigatorVerdict) -> str:
    """Plain-text view that goes in the artifact's `raw` field."""
    lines: list[str] = []
    lines.append(f"# Investigation dossier — {d.ticket_key}")
    lines.append("")
    lines.append(f"## Verdict: {'✓ SUFFICIENT' if v.sufficient else '⚠ MORE WORK NEEDED'}  (confidence: {v.confidence})")
    lines.append(v.reasoning or "(no reasoning supplied)")
    if v.target_repos:
        lines.append(f"\nRecommended repo(s): {', '.join(v.target_repos)}")
    if v.existing_pr_url:
        lines.append(f"Existing PR: {v.existing_pr_url}")
    if v.additional_work:
        lines.append("\nAdditional work required:")
        for item in v.additional_work:
            lines.append(f"  - {item}")
    lines.append("")
    if d.open_prs:
        lines.append(f"## Open PRs ({len(d.open_prs)})")
        for p in d.open_prs[:5]:
            tag = " [DRAFT]" if p.draft else ""
            lines.append(f"  • #{p.number} {p.repo_full_name}{tag}: {p.title}")
            lines.append(f"      → {p.html_url}")
            lines.append(f"      author=@{p.author} branch={p.head_branch} → {p.base_branch} files={p.changed_files} +{p.additions}/-{p.deletions}")
    if d.other_prs:
        lines.append(f"\n## Other PRs ({len(d.other_prs)})")
        for p in d.other_prs[:3]:
            status = "MERGED" if p.merged else p.state.upper()
            lines.append(f"  • [{status}] #{p.number} {p.repo_full_name}: {p.title}")
    if d.local_evidence:
        lines.append(f"\n## Local clones with ticket-key signals ({len(d.local_evidence)})")
        for ev in d.local_evidence[:5]:
            lines.append(f"  • {ev.repo_name} (score={ev.score})")
            if ev.branches:
                lines.append(f"      branches: {', '.join(ev.branches[:3])}")
            if ev.commits:
                lines.append(f"      recent commits referencing {d.ticket_key}: {len(ev.commits)}")
            if ev.files_with_mentions:
                lines.append(f"      files mentioning {d.ticket_key}: {len(ev.files_with_mentions)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude prompt
# ---------------------------------------------------------------------------

INVESTIGATOR_SYSTEM_PROMPT = """You are the Investigator agent for a multi-agent
software team. Before any code-writing agent runs, you assess whether a Jira
ticket needs new work or whether existing work (an open PR) already addresses it.

You receive:
  1. The Jira ticket (key, summary, description, acceptance criteria).
  2. A discovery dossier listing repos with branches/commits referencing the
     ticket, and any open or recent PRs whose title or body mentions it,
     including a short diff excerpt and a per-file change summary.

Your job is to produce a single JSON object with this exact shape:
{
  "target_repos": ["owner/repo or local path"],
  "existing_pr_url": "...",       // empty string if none
  "sufficient": true | false,
  "reasoning": "2-3 sentences explaining your verdict",
  "additional_work": ["short bullet describing each remaining item"],
  "confidence": "low" | "medium" | "high"
}

Rules:
- "sufficient: true" ONLY if you can show that the open PR's diff plausibly
  satisfies every acceptance criterion in the ticket.
- If the PR is open but partial, set sufficient: false and list the
  remaining items in additional_work.
- If multiple repos appear in the dossier, list ALL repos that need
  changes in target_repos.
- If you cannot confidently identify a target repo from the dossier, set
  target_repos: [] and confidence: "low".
- Output ONLY the JSON. No prose around it.
"""


async def investigate(
    ticket_key: str,
    ticket: dict[str, Any],
    *,
    local_root: str,
    github_token: str = "",
    model: str = "claude-haiku-4-5-20251001",
) -> InvestigationResult:
    """Run discovery + Claude assessment. Returns a verdict + the dossier."""
    # Emit a "thought" so the live panel for the investigator opens
    _emit_agent_thought(INVESTIGATOR_AGENT_ID, "prompt",
                        f"Building dossier for {ticket_key} (searching local clones + GitHub PRs)…")

    dossier = await build_dossier(ticket_key, local_root=local_root, github_token=github_token)

    log.info("dossier_built",
             ticket_key=ticket_key,
             local_hits=len(dossier.local_evidence),
             open_prs=len(dossier.open_prs),
             other_prs=len(dossier.other_prs))

    # Build the Claude prompt
    ticket_text = (
        f"Ticket key: {ticket_key}\n"
        f"Summary: {ticket.get('summary','')}\n"
        f"Issue type: {ticket.get('issue_type','')}\n"
        f"Priority: {ticket.get('priority','')}\n"
        f"Labels: {', '.join(ticket.get('labels') or [])}\n"
        f"Components: {', '.join(ticket.get('components') or [])}\n"
        f"Description:\n{ticket.get('description','')[:3000]}\n"
    )
    ac = ticket.get("acceptance_criteria") or []
    if ac:
        ticket_text += "\nAcceptance criteria:\n"
        for item in ac:
            ticket_text += f"- {item}\n"

    dossier_text = _format_dossier_text(dossier, InvestigatorVerdict())

    # Add the diff excerpts inline so Claude can actually assess sufficiency
    if dossier.open_prs:
        dossier_text += "\n\n## Open PR diffs (excerpt)\n"
        for p in dossier.open_prs[:2]:
            dossier_text += f"\n### PR #{p.number} {p.repo_full_name}\n```diff\n{p.diff_excerpt}\n```\n"

    user_msg = f"## Ticket\n{ticket_text}\n## Dossier\n{dossier_text}"

    _emit_agent_thought(INVESTIGATOR_AGENT_ID, "prompt",
                        f"Asking Claude to assess sufficiency. Dossier: {len(dossier.local_evidence)} local hits, {len(dossier.open_prs)} open PRs.")

    # Use ClaudeMixin via a tiny helper class so the call appears in agent_thought stream
    class _Caller(ClaudeMixin):
        agent_id = INVESTIGATOR_AGENT_ID

    caller = _Caller()
    raw = ""
    verdict = InvestigatorVerdict(confidence="low",
                                  reasoning="Claude unavailable; fell back to dossier heuristics.")
    try:
        result = await caller.call_claude(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=INVESTIGATOR_SYSTEM_PROMPT,
            model=model,
            max_tokens=1500,
        )
        raw = (result.get("content") or "").strip()
        # Try to extract JSON (model may wrap in fences or include preamble)
        parsed = _extract_json(raw)
        if isinstance(parsed, dict):
            verdict = InvestigatorVerdict(
                target_repos=list(parsed.get("target_repos") or []),
                existing_pr_url=str(parsed.get("existing_pr_url") or ""),
                sufficient=bool(parsed.get("sufficient")),
                reasoning=str(parsed.get("reasoning") or ""),
                additional_work=list(parsed.get("additional_work") or []),
                confidence=str(parsed.get("confidence") or "medium"),
            )
    except Exception as e:
        log.warning("investigator_claude_failed", error=str(e)[:200])
        # Fallback: heuristic verdict from dossier
        if dossier.open_prs:
            top = dossier.open_prs[0]
            verdict = InvestigatorVerdict(
                target_repos=[top.repo_full_name],
                existing_pr_url=top.html_url,
                sufficient=False,
                reasoning=f"Claude unavailable. Heuristic: open PR #{top.number} on {top.repo_full_name} mentions the ticket but sufficiency cannot be assessed automatically.",
                confidence="low",
            )
        elif dossier.recommended_repo_github or dossier.recommended_repo_local:
            verdict = InvestigatorVerdict(
                target_repos=[dossier.recommended_repo_github or dossier.recommended_repo_local],
                sufficient=False,
                reasoning="Claude unavailable. Heuristic: best-match repo from local clone scan.",
                confidence="low",
            )

    _emit_agent_thought(INVESTIGATOR_AGENT_ID, "response",
                        f"Verdict: {'sufficient' if verdict.sufficient else 'needs work'} (confidence: {verdict.confidence})\n{verdict.reasoning[:500]}")

    return InvestigationResult(dossier=dossier, verdict=verdict, raw_claude_output=raw)


def _extract_json(raw: str) -> Any:
    """Pull a JSON object out of a Claude response that may be wrapped in fences."""
    s = raw.strip()
    if s.startswith("```"):
        # Drop the leading ``` and optional 'json' label
        s = s.split("\n", 1)[1] if "\n" in s else ""
        # Drop trailing ```
        if s.endswith("```"):
            s = s[: -3].strip()
    try:
        return json.loads(s)
    except Exception:
        # Fallback: find the first { ... } block
        i = s.find("{")
        if i < 0:
            return None
        # Naive matching — fine for the model's output shape
        depth = 0
        for j in range(i, len(s)):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[i : j + 1])
                    except Exception:
                        return None
        return None
