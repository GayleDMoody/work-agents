"""
AgentBus — inter-agent communication system.

Enables agents to:
  1. Send direct messages to specific agents
  2. Ask another agent a question and get a response (synchronous)
  3. Broadcast to all agents
  4. Read the shared message log

This is the "office Slack" for the AI team.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.observability.logging import get_logger

log = get_logger("agent_bus")


class MessageType(str, Enum):
    DIRECT = "direct"           # One agent → another
    QUESTION = "question"       # Agent asks another agent, expects reply
    REPLY = "reply"             # Response to a question
    BROADCAST = "broadcast"     # To all agents
    FEEDBACK = "feedback"       # Structured feedback (e.g., QA → Backend)
    HANDOFF = "handoff"         # Passing work to another agent


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: MessageType
    from_agent: str
    to_agent: str = ""          # empty = broadcast
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    reply_to: str = ""          # message id this is replying to
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentBus:
    """
    Central message bus that all agents share within a Crew run.

    Agents interact with the bus via helper methods on BaseAgent:
        await self.send_message("qa", "Can you check if auth is tested?")
        reply = await self.ask_agent("architect", "What pattern should I use for the cache?")
        await self.broadcast("Backend API is ready for integration")
    """

    def __init__(self):
        self.messages: list[Message] = []
        self._agents: dict[str, Any] = {}  # agent_id -> BaseAgent instance
        self._pending_questions: dict[str, asyncio.Future] = {}

    def register_agent(self, agent_id: str, agent: Any) -> None:
        """Register an agent so it can receive messages."""
        self._agents[agent_id] = agent

    def register_all(self, agents: list[Any]) -> None:
        """Register all agents in the crew."""
        for agent in agents:
            self._agents[agent.agent_id] = agent

    # ------------------------------------------------------------------
    # Send operations
    # ------------------------------------------------------------------

    async def send(self, from_agent: str, to_agent: str, content: str,
                   msg_type: MessageType = MessageType.DIRECT,
                   metadata: dict[str, Any] | None = None) -> Message:
        """Send a message from one agent to another."""
        msg = Message(
            type=msg_type,
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        # Stream into the thought-feed so dashboard chat panels show inter-agent comms.
        try:
            from src.agents.claude_mixin import _emit_agent_thought
            label = f"to {to_agent}" if to_agent and to_agent != "*" else "to everyone"
            _emit_agent_thought(from_agent, "message_sent",
                                f"[{msg_type.value} {label}] {content[:6000]}")
            if to_agent and to_agent != "*":
                _emit_agent_thought(to_agent, "message_received",
                                    f"[{msg_type.value} from {from_agent}] {content[:6000]}")
        except Exception:
            pass
        log.info("message_sent", from_agent=from_agent, to_agent=to_agent,
                 type=msg_type.value, content=content[:80])
        return msg

    async def broadcast(self, from_agent: str, content: str,
                        metadata: dict[str, Any] | None = None) -> Message:
        """Broadcast a message to all agents."""
        msg = Message(
            type=MessageType.BROADCAST,
            from_agent=from_agent,
            to_agent="*",
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        log.info("broadcast", from_agent=from_agent, content=content[:80])
        return msg

    async def ask(self, from_agent: str, to_agent: str, question: str) -> str:
        """
        Ask another agent a question and wait for a response.
        The target agent processes the question via its Claude instance.
        """
        # Record the question
        q_msg = Message(
            type=MessageType.QUESTION,
            from_agent=from_agent,
            to_agent=to_agent,
            content=question,
        )
        self.messages.append(q_msg)
        log.info("question_asked", from_agent=from_agent, to_agent=to_agent,
                 question=question[:80])

        # Get the target agent and have it respond
        target = self._agents.get(to_agent)
        if not target:
            reply_text = f"[Agent '{to_agent}' not found in the crew]"
        else:
            try:
                reply_text = await self._get_agent_reply(target, from_agent, question)
            except Exception as e:
                reply_text = f"[Error getting reply from {to_agent}: {str(e)[:100]}]"

        # Record the reply
        r_msg = Message(
            type=MessageType.REPLY,
            from_agent=to_agent,
            to_agent=from_agent,
            content=reply_text,
            reply_to=q_msg.id,
        )
        self.messages.append(r_msg)
        log.info("question_answered", from_agent=to_agent, to_agent=from_agent,
                 reply=reply_text[:80])

        return reply_text

    async def send_feedback(self, from_agent: str, to_agent: str,
                            feedback: str, metadata: dict[str, Any] | None = None) -> Message:
        """Send structured feedback (e.g., QA telling Backend about test failures)."""
        return await self.send(
            from_agent=from_agent,
            to_agent=to_agent,
            content=feedback,
            msg_type=MessageType.FEEDBACK,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_messages_for(self, agent_id: str) -> list[Message]:
        """Get all messages relevant to an agent (sent to them or broadcast)."""
        return [
            m for m in self.messages
            if m.to_agent == agent_id or m.to_agent == "*" or m.from_agent == agent_id
        ]

    def get_unread_for(self, agent_id: str, since_index: int = 0) -> list[Message]:
        """Get messages since a given index (for incremental reads)."""
        relevant = self.get_messages_for(agent_id)
        return relevant[since_index:]

    def get_conversation(self, agent_a: str, agent_b: str) -> list[Message]:
        """Get the conversation between two agents."""
        return [
            m for m in self.messages
            if (m.from_agent == agent_a and m.to_agent == agent_b) or
               (m.from_agent == agent_b and m.to_agent == agent_a)
        ]

    def get_full_log(self) -> list[dict[str, Any]]:
        """Get the full message log as dicts (for UI/API)."""
        return [m.model_dump() for m in self.messages]

    def format_inbox(self, agent_id: str) -> str:
        """Format an agent's messages as a readable string for context injection."""
        msgs = self.get_messages_for(agent_id)
        if not msgs:
            return ""
        lines = ["## Team Messages\n"]
        for m in msgs[-10:]:  # Last 10 messages
            direction = "→ you" if m.to_agent == agent_id else f"→ {m.to_agent}"
            if m.to_agent == "*":
                direction = "→ everyone"
            icon = {"question": "❓", "reply": "💬", "feedback": "⚠️", "broadcast": "📢"}.get(m.type.value, "✉️")
            lines.append(f"{icon} **{m.from_agent}** {direction}: {m.content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_agent_reply(self, agent: Any, from_agent: str, question: str) -> str:
        """Have an agent generate a reply to a question using Claude."""
        if not hasattr(agent, 'call_claude'):
            return f"[{agent.agent_id} cannot respond — no Claude integration]"

        response = await agent.call_claude(
            messages=[{
                "role": "user",
                "content": (
                    f"Your colleague {from_agent} is asking you a question. "
                    f"Answer concisely based on your expertise as a {agent.role}.\n\n"
                    f"Question: {question}"
                ),
            }],
            system_prompt=agent.system_prompt,
            model=agent.model,
            max_tokens=1024,
        )
        return response.get("content", "")
