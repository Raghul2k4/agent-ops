"""Schemas for the workspace policy document and the approval lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RiskLevel = Literal["low", "medium", "high", "critical"]
ApprovalDecision = Literal["approve", "reject", "request_changes"]


class PolicyUpdateRequest(BaseModel):
    """Update the workspace policy document. Every field is optional."""

    model_config = ConfigDict(extra="forbid")

    tool_allowlist: list[str] | None = Field(
        default=None,
        description="Tool names that may run. An empty list allows every registered tool.",
    )
    blocked_tools: list[str] | None = Field(
        default=None, description="Tool names that may never run. The deny list always wins."
    )
    disabled_agent_ids: list[uuid.UUID] | None = Field(
        default=None, description="Agents that are switched off for this workspace."
    )
    require_approval_for_risk_levels: list[RiskLevel] | None = Field(
        default=None,
        description="Risk levels that require a human decision before the tool runs.",
    )
    tool_rate_limits: dict[str, int] | None = Field(
        default=None, description="Maximum calls per minute, per tool name."
    )
    max_tool_calls_per_run: int | None = Field(default=None, ge=1, le=1000)
    max_runs_per_hour: int | None = Field(default=None, ge=1, le=100000)
    approval_ttl_minutes: int | None = Field(default=None, ge=1, le=10080)
    execution_paused: bool | None = Field(
        default=None, description="Emergency pause: no new run may start."
    )
    paused_reason: str | None = Field(default=None, max_length=500)
    change_note: str | None = Field(
        default=None, max_length=500, description="Recorded in the audit trail."
    )

    @field_validator("tool_allowlist", "blocked_tools")
    @classmethod
    def _normalise_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        names = {name.strip() for name in value if name.strip()}
        return sorted(names)

    @field_validator("tool_rate_limits")
    @classmethod
    def _validate_limits(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        for name, limit in value.items():
            if not name.strip():
                raise ValueError("A rate limit must name a tool.")
            if limit < 1:
                raise ValueError("A rate limit must be at least one call per minute.")
        return {name.strip(): int(limit) for name, limit in value.items()}


class PolicyRead(BaseModel):
    """The effective policy document for a workspace."""

    workspace_id: uuid.UUID
    version: int
    tool_allowlist: list[str]
    blocked_tools: list[str]
    disabled_agent_ids: list[uuid.UUID]
    require_approval_for_risk_levels: list[str]
    tool_rate_limits: dict[str, int]
    max_tool_calls_per_run: int | None
    max_runs_per_hour: int | None
    approval_ttl_minutes: int
    execution_paused: bool
    paused_reason: str | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ApprovalRead(BaseModel):
    """One approval request."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    agent_version_id: uuid.UUID | None
    tool_definition_id: uuid.UUID | None
    tool_name: str
    risk_level: str
    canonical_arguments_hash: str
    arguments: dict[str, Any]
    requested_by: uuid.UUID | None
    status: str
    decision: str | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    review_note: str | None
    policy_version: int
    expires_at: datetime
    created_at: datetime
    is_expired: bool = False


class ApprovalDecisionRequest(BaseModel):
    """A reviewer's decision on a pending approval.

    ``arguments_hash`` is the hash the reviewer was shown. It must match the
    stored canonical hash, so a payload that changed after the review started
    can never be approved.
    """

    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecision
    arguments_hash: str = Field(min_length=64, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class ApprovalDecisionResponse(BaseModel):
    """The outcome of a decision, including what happened to the run."""

    approval: ApprovalRead
    run_status: str
    run_id: uuid.UUID
    message: str


__all__ = [
    "ApprovalDecision",
    "ApprovalDecisionRequest",
    "ApprovalDecisionResponse",
    "ApprovalRead",
    "PolicyRead",
    "PolicyUpdateRequest",
    "RiskLevel",
]
