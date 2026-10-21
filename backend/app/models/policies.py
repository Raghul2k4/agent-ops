"""Workspace policy, approval request and run-checkpoint ORM mappings.

The policy document is the workspace's enforcement surface: which tools may
run, which agent versions need approval, what the rate limits are and whether
execution is paused. Approval requests bind a proposed action to the exact
canonical argument hash so a decision can never authorise a different action.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONPayload, UUIDPrimaryKeyMixin

APPROVAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "changes_requested",
    "expired",
    "executed",
    "revoked",
)
APPROVAL_DECISIONS = ("approve", "reject", "request_changes")
RISK_LEVELS = ("low", "medium", "high", "critical")


class WorkspacePolicy(Base):
    """One policy document per workspace."""

    __tablename__ = "workspace_policies"
    __table_args__ = (
        CheckConstraint("version >= 1", name="workspace_policies_version_positive"),
        CheckConstraint(
            "approval_ttl_minutes between 1 and 10080",
            name="workspace_policies_ttl_range",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    tool_allowlist: Mapped[list[str]] = mapped_column(
        JSONPayload, nullable=False, default=list, server_default="[]"
    )
    blocked_tools: Mapped[list[str]] = mapped_column(
        JSONPayload, nullable=False, default=list, server_default="[]"
    )
    disabled_agent_ids: Mapped[list[str]] = mapped_column(
        JSONPayload, nullable=False, default=list, server_default="[]"
    )
    require_approval_for_risk_levels: Mapped[list[str]] = mapped_column(
        JSONPayload,
        nullable=False,
        default=lambda: ["high", "critical"],
        server_default='["high", "critical"]',
    )
    tool_rate_limits: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    max_tool_calls_per_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_runs_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_ttl_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    execution_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    paused_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ApprovalRequest(UUIDPrimaryKeyMixin, Base):
    """A proposed action that a human must approve before it can run."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(f"status IN {APPROVAL_STATUSES}", name="approval_requests_status_valid"),
        CheckConstraint(f"risk_level IN {RISK_LEVELS}", name="approval_requests_risk_valid"),
        Index("ix_approval_requests_workspace_status", "workspace_id", "status", "created_at"),
        Index("ix_approval_requests_run", "run_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    tool_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_definitions.id", ondelete="SET NULL"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    canonical_arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default="pending"
    )
    decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RunCheckpoint(UUIDPrimaryKeyMixin, Base):
    """The state needed to continue a run that paused for approval."""

    __tablename__ = "run_checkpoints"
    __table_args__ = (Index("ix_run_checkpoints_run_step", "run_id", "step"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "APPROVAL_DECISIONS",
    "APPROVAL_STATUSES",
    "RISK_LEVELS",
    "ApprovalRequest",
    "RunCheckpoint",
    "WorkspacePolicy",
]
