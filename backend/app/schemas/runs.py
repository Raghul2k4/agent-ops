"""Schemas for run history, events, traces and cancellation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunCreateRequest(BaseModel):
    """Start a run for an agent version."""

    model_config = ConfigDict(extra="forbid")

    agent_id: uuid.UUID
    version_id: uuid.UUID | None = None
    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input")
    @classmethod
    def _require_message(cls, value: dict[str, Any]) -> dict[str, Any]:
        message = value.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("input.message must be a non-empty string")
        if len(message) > 16000:
            raise ValueError("input.message must be at most 16000 characters")
        return value


class RunRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    agent_version_id: uuid.UUID
    version_number: int | None = None
    initiated_by: uuid.UUID | None = None
    status: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    model_config_id: uuid.UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    estimated_cost: float | None = None
    error_code: str | None = None
    error_summary: str | None = None
    replay_of_run_id: uuid.UUID | None = None
    created_at: datetime


class RunEventRead(BaseModel):
    id: uuid.UUID
    sequence_number: int
    event_type: str
    event_status: str
    payload: dict[str, Any]
    occurred_at: datetime


class TraceSpanRead(BaseModel):
    id: uuid.UUID
    parent_span_id: uuid.UUID | None = None
    span_type: str
    name: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    attributes: dict[str, Any]


class RunEventList(BaseModel):
    items: list[RunEventRead]
    last_sequence: int
    run_status: str
    has_more: bool = False


class TraceView(BaseModel):
    run_id: uuid.UUID
    spans: list[TraceSpanRead]


__all__ = [
    "RunCreateRequest",
    "RunEventList",
    "RunEventRead",
    "RunRead",
    "TraceSpanRead",
    "TraceView",
]
