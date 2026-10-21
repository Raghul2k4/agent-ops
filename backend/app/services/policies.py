"""Workspace policy: the server-side enforcement surface for executions.

The policy document is the only place that decides whether a run may start,
which tools it may call, which of those calls need a human decision and how
fast it may go. It is read on every run and every tool call, so the checks
here are the security boundary — the prompt is not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PolicyViolation, RateLimited
from app.models.policies import WorkspacePolicy
from app.models.runs import AgentRun, RunEvent
from app.schemas.policies import PolicyUpdateRequest
from app.tools.base import ToolSpec

DEFAULT_APPROVAL_RISK_LEVELS: tuple[str, ...] = ("high", "critical")


@dataclass(frozen=True, slots=True)
class EffectivePolicy:
    """The policy values the runtime enforces, resolved once per operation."""

    workspace_id: uuid.UUID
    version: int
    tool_allowlist: frozenset[str]
    blocked_tools: frozenset[str]
    disabled_agent_ids: frozenset[uuid.UUID]
    require_approval_for_risk_levels: frozenset[str]
    tool_rate_limits: dict[str, int]
    max_tool_calls_per_run: int | None
    max_runs_per_hour: int | None
    approval_ttl_minutes: int
    execution_paused: bool
    paused_reason: str | None

    def tool_is_allowed(self, tool_name: str) -> bool:
        """The deny list always wins over the allow list."""
        if tool_name in self.blocked_tools:
            return False
        if not self.tool_allowlist:
            return True
        return tool_name in self.tool_allowlist

    def requires_approval(self, spec: ToolSpec) -> bool:
        """Whether this tool needs a human decision before it may run."""
        if spec.requires_approval:
            return True
        return spec.risk_level in self.require_approval_for_risk_levels

    def tool_call_limit(self, configured: int) -> int:
        """The tighter of the agent's own limit and the workspace override."""
        if self.max_tool_calls_per_run is None:
            return configured
        return min(configured, self.max_tool_calls_per_run)

    def rate_limit_for(self, tool_name: str) -> int | None:
        return self.tool_rate_limits.get(tool_name)


def _default_policy(workspace_id: uuid.UUID) -> WorkspacePolicy:
    return WorkspacePolicy(
        workspace_id=workspace_id,
        version=1,
        tool_allowlist=[],
        blocked_tools=[],
        disabled_agent_ids=[],
        require_approval_for_risk_levels=list(DEFAULT_APPROVAL_RISK_LEVELS),
        tool_rate_limits={},
        max_tool_calls_per_run=None,
        max_runs_per_hour=None,
        approval_ttl_minutes=60,
        execution_paused=False,
        paused_reason=None,
    )


async def get_policy_row(session: AsyncSession, *, workspace_id: uuid.UUID) -> WorkspacePolicy:
    """Return the policy row, creating a default document on first use."""
    row = await session.scalar(
        select(WorkspacePolicy).where(WorkspacePolicy.workspace_id == workspace_id)
    )
    if row is None:
        row = _default_policy(workspace_id)
        session.add(row)
        await session.flush()
    return row


async def get_policy(session: AsyncSession, *, workspace_id: uuid.UUID) -> EffectivePolicy:
    """Return the effective policy for a workspace."""
    row = await get_policy_row(session, workspace_id=workspace_id)
    return effective_policy(row)


def effective_policy(row: WorkspacePolicy) -> EffectivePolicy:
    """Project a stored row onto the values the runtime enforces."""
    return EffectivePolicy(
        workspace_id=row.workspace_id,
        version=row.version,
        tool_allowlist=frozenset(row.tool_allowlist or ()),
        blocked_tools=frozenset(row.blocked_tools or ()),
        disabled_agent_ids=frozenset(uuid.UUID(str(item)) for item in row.disabled_agent_ids or ()),
        require_approval_for_risk_levels=frozenset(row.require_approval_for_risk_levels or ()),
        tool_rate_limits=dict(row.tool_rate_limits or {}),
        max_tool_calls_per_run=row.max_tool_calls_per_run,
        max_runs_per_hour=row.max_runs_per_hour,
        approval_ttl_minutes=row.approval_ttl_minutes,
        execution_paused=bool(row.execution_paused),
        paused_reason=row.paused_reason,
    )


async def update_policy(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    payload: PolicyUpdateRequest,
    actor_id: uuid.UUID | None,
) -> WorkspacePolicy:
    """Apply a policy change and bump the policy version.

    The version is stamped onto runs and approval requests, so a decision can
    be traced back to the policy that was in force when the action was
    proposed.
    """
    row = await get_policy_row(session, workspace_id=workspace_id)
    if payload.tool_allowlist is not None:
        row.tool_allowlist = payload.tool_allowlist
    if payload.blocked_tools is not None:
        row.blocked_tools = payload.blocked_tools
    if payload.disabled_agent_ids is not None:
        row.disabled_agent_ids = [str(agent_id) for agent_id in payload.disabled_agent_ids]
    if payload.require_approval_for_risk_levels is not None:
        row.require_approval_for_risk_levels = list(payload.require_approval_for_risk_levels)
    if payload.tool_rate_limits is not None:
        row.tool_rate_limits = dict(payload.tool_rate_limits)
    if payload.max_tool_calls_per_run is not None:
        row.max_tool_calls_per_run = payload.max_tool_calls_per_run
    if payload.max_runs_per_hour is not None:
        row.max_runs_per_hour = payload.max_runs_per_hour
    if payload.approval_ttl_minutes is not None:
        row.approval_ttl_minutes = payload.approval_ttl_minutes
    if payload.execution_paused is not None:
        row.execution_paused = payload.execution_paused
        if not payload.execution_paused:
            row.paused_reason = None
    if payload.paused_reason is not None:
        row.paused_reason = payload.paused_reason
    row.updated_by = actor_id
    row.version = row.version + 1
    await session.flush()
    return row


def assert_execution_allowed(policy: EffectivePolicy, *, agent_id: uuid.UUID) -> None:
    """Refuse to start a run when the workspace paused execution."""
    if policy.execution_paused:
        reason = policy.paused_reason or "No reason was given."
        raise PolicyViolation(
            f"Execution is paused for this workspace: {reason}",
            details={"policy_version": policy.version, "paused": True},
        )
    if agent_id in policy.disabled_agent_ids:
        raise PolicyViolation(
            "This agent is disabled for the workspace.",
            details={"agent_id": str(agent_id), "policy_version": policy.version},
        )


async def assert_run_quota(session: AsyncSession, *, policy: EffectivePolicy) -> None:
    """Enforce the workspace run quota (runs started in the last hour)."""
    if policy.max_runs_per_hour is None:
        return
    since = datetime.now(UTC) - timedelta(hours=1)
    recent = int(
        await session.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.workspace_id == policy.workspace_id,
                AgentRun.created_at >= since,
            )
        )
        or 0
    )
    if recent >= policy.max_runs_per_hour:
        raise RateLimited(
            "The workspace run quota for this hour has been reached.",
            details={"max_runs_per_hour": policy.max_runs_per_hour, "recent": recent},
        )


async def assert_tool_rate(
    session: AsyncSession, *, policy: EffectivePolicy, tool_name: str
) -> None:
    """Enforce the per-tool call rate limit (calls per minute)."""
    limit = policy.rate_limit_for(tool_name)
    if limit is None:
        return
    since = datetime.now(UTC) - timedelta(minutes=1)
    recent = int(
        await session.scalar(
            select(func.count())
            .select_from(RunEvent)
            .where(
                RunEvent.workspace_id == policy.workspace_id,
                RunEvent.event_type == "tool.request",
                RunEvent.occurred_at >= since,
                RunEvent.payload["tool"].astext == tool_name,
            )
        )
        or 0
    )
    if recent >= limit:
        raise RateLimited(
            f"The rate limit for '{tool_name}' has been reached.",
            details={"tool": tool_name, "limit_per_minute": limit, "recent": recent},
        )


def policy_read(row: WorkspacePolicy) -> dict[str, Any]:
    """Serialise the policy document for the API."""
    return {
        "workspace_id": row.workspace_id,
        "version": row.version,
        "tool_allowlist": list(row.tool_allowlist or ()),
        "blocked_tools": list(row.blocked_tools or ()),
        "disabled_agent_ids": [uuid.UUID(str(item)) for item in row.disabled_agent_ids or ()],
        "require_approval_for_risk_levels": list(row.require_approval_for_risk_levels or ()),
        "tool_rate_limits": dict(row.tool_rate_limits or {}),
        "max_tool_calls_per_run": row.max_tool_calls_per_run,
        "max_runs_per_hour": row.max_runs_per_hour,
        "approval_ttl_minutes": row.approval_ttl_minutes,
        "execution_paused": bool(row.execution_paused),
        "paused_reason": row.paused_reason,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


__all__ = [
    "DEFAULT_APPROVAL_RISK_LEVELS",
    "EffectivePolicy",
    "assert_execution_allowed",
    "assert_run_quota",
    "assert_tool_rate",
    "effective_policy",
    "get_policy",
    "get_policy_row",
    "policy_read",
    "update_policy",
]
