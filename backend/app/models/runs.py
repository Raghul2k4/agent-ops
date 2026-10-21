"""Agent run, event and trace-span ORM mappings.

Events are persisted in order with a per-run sequence number; the client can
recover missed events with ``after_seq`` instead of relying on a socket.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONPayload, UUIDPrimaryKeyMixin

RUN_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled", "awaiting_approval")
EVENT_STATUSES = ("ok", "error", "warning", "info")
SPAN_STATUSES = ("running", "ok", "error", "cancelled")


class AgentRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(f"status IN {RUN_STATUSES}", name="agent_runs_status_valid"),
        Index("ix_agent_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_agent_runs_workspace_status", "workspace_id", "status"),
        Index("ix_agent_runs_agent_created", "agent_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=False
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    input: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONPayload, nullable=True)
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    replay_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    pending_approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    replay_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RunEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_number", name="run_events_sequence_unique"),
        CheckConstraint(f"event_status IN {EVENT_STATUSES}", name="run_events_status_valid"),
        Index("ix_run_events_run_sequence", "run_id", "sequence_number"),
        Index("ix_run_events_workspace_occurred", "workspace_id", "occurred_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TraceSpan(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "trace_spans"
    __table_args__ = (
        CheckConstraint(f"status IN {SPAN_STATUSES}", name="trace_spans_status_valid"),
        Index("ix_trace_spans_run_started", "run_id", "started_at"),
        Index("ix_trace_spans_parent", "parent_span_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    parent_span_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trace_spans.id", ondelete="CASCADE"), nullable=True
    )
    span_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )


__all__ = [
    "EVENT_STATUSES",
    "RUN_STATUSES",
    "SPAN_STATUSES",
    "AgentRun",
    "RunEvent",
    "TraceSpan",
]
