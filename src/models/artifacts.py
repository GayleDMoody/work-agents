"""Artifact models for agent outputs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    DOCUMENT = "document"
    CODE = "code"
    TEST = "test"
    CONFIG = "config"
    REVIEW = "review"
    PLAN = "plan"
    ARCHITECTURE = "architecture"


class Artifact(BaseModel):
    """An output produced by an agent."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    artifact_type: ArtifactType
    name: str
    content: str
    file_path: Optional[str] = None
    agent_id: str
    phase: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_context_dict(self) -> dict[str, Any]:
        """Convert to dict for SharedContext.artifacts."""
        return {
            "id": self.id,
            "artifact_type": self.artifact_type.value,
            "name": self.name,
            "content": self.content,
            "file_path": self.file_path,
            "agent_id": self.agent_id,
            "phase": self.phase,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
