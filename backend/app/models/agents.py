"""Agent and immutable agent-version ORM mappings.

``Agent.draft_configuration`` holds the mutable working copy. Publishing
serialises that configuration into a new ``AgentVersion`` row; an UPDATE
trigger in the migration rejects any later mutation of a version.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONPayload, TimestampMixin, UUIDPrimaryKeyMixin

AGENT_STATUSES = ("draft", "published", "archived")


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An agent definition and its editable draft configuration."""

    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(f"status IN {AGENT_STATUSES}", name="agents_status_valid"),
        Index("ix_agents_workspace_updated", "workspace_id", "updated_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    draft_configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    current_published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )


class AgentVersion(UUIDPrimaryKeyMixin, Base):
    """An immutable, published snapshot of an agent configuration."""

    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="agent_versions_number_unique"),
        Index("ix_agent_versions_agent_created", "agent_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONPayload, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["AGENT_STATUSES", "Agent", "AgentVersion"]
