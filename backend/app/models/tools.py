"""Tool registry ORM mappings.

``ToolDefinition.implementation`` is a server-side registry key, never code
supplied by a caller. Global built-ins have ``workspace_id IS NULL``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONPayload, TimestampMixin, UUIDPrimaryKeyMixin

RISK_LEVELS = ("low", "medium", "high", "critical")


class ToolDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered tool contract."""

    __tablename__ = "tool_definitions"
    __table_args__ = (
        CheckConstraint(f"risk_level IN {RISK_LEVELS}", name="tool_definitions_risk_valid"),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 600", name="tool_definitions_timeout_valid"),
        CheckConstraint("max_retries BETWEEN 0 AND 5", name="tool_definitions_retries_valid"),
        Index("ix_tool_definitions_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    output_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    required_permissions: Mapped[list[str]] = mapped_column(
        JSONPayload, nullable=False, default=list, server_default="[]"
    )
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    implementation: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AgentTool(UUIDPrimaryKeyMixin, Base):
    """Association between an immutable agent version and a tool."""

    __tablename__ = "agent_tools"
    __table_args__ = (
        UniqueConstraint("agent_version_id", "tool_definition_id", name="agent_tools_unique"),
        Index("ix_agent_tools_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False
    )
    tool_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )


__all__ = ["RISK_LEVELS", "AgentTool", "ToolDefinition"]
