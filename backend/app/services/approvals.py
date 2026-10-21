"""Approval lifecycle: propose, review, decide, execute.

An approval request is bound to the **exact** action it describes: the tool
name, the canonical argument payload and its SHA-256 hash. A decision is
accepted only when the reviewer quotes the same hash they were shown, the
request is still pending and it has not expired. The action is re-validated
against the current policy immediately before it executes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApprovalExpired,
    ApprovalMismatch,
    ConflictError,
    ResourceNotFound,
)
from app.models.policies import ApprovalRequest

#: Statuses that no longer accept a decision.
FINAL_STATUSES = frozenset({"rejected", "changes_requested", "expired", "executed", "revoked"})


def is_expired(approval: ApprovalRequest, *, now: datetime | None = None) -> bool:
    """Whether the request may no longer be decided."""
    moment = now or datetime.now(UTC)
    return approval.expires_at <= moment


async def create_approval_request(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    agent_version_id: uuid.UUID | None,
    tool_definition_id: uuid.UUID | None,
    tool_name: str,
    risk_level: str,
    arguments: dict[str, Any],
    canonical_hash: str,
    policy_version: int,
    ttl_minutes: int,
    requested_by: uuid.UUID | None,
) -> ApprovalRequest:
    """Record a proposed action that needs a human decision."""
    approval = ApprovalRequest(
        workspace_id=workspace_id,
        run_id=run_id,
        agent_version_id=agent_version_id,
        tool_definition_id=tool_definition_id,
        tool_name=tool_name,
        risk_level=risk_level,
        canonical_arguments_hash=canonical_hash,
        arguments=arguments,
        requested_by=requested_by,
        status="pending",
        policy_version=policy_version,
        expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    )
    session.add(approval)
    await session.flush()
    return approval


async def get_approval(
    session: AsyncSession, *, workspace_id: uuid.UUID, approval_id: uuid.UUID
) -> ApprovalRequest:
    """Return one approval request scoped to the workspace."""
    row = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.id == approval_id,
        )
    )
    if row is None:
        raise ResourceNotFound("Approval request not found.")
    return row


async def list_approvals(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    status: str | None = None,
    run_id: uuid.UUID | None = None,
    tool_name: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[ApprovalRequest], int]:
    """List approval requests, newest first."""
    conditions = [ApprovalRequest.workspace_id == workspace_id]
    if status:
        conditions.append(ApprovalRequest.status == status)
    if run_id:
        conditions.append(ApprovalRequest.run_id == run_id)
    if tool_name:
        conditions.append(ApprovalRequest.tool_name == tool_name)

    total = int(
        await session.scalar(select(func.count()).select_from(ApprovalRequest).where(*conditions))
        or 0
    )
    rows = (
        await session.scalars(
            select(ApprovalRequest)
            .where(*conditions)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), total


async def decide(
    session: AsyncSession,
    *,
    approval: ApprovalRequest,
    decision: str,
    reviewer_id: uuid.UUID | None,
    note: str | None,
    arguments_hash: str,
) -> ApprovalRequest:
    """Apply a reviewer's decision to a pending request.

    The request must still be pending, must not have expired and the hash the
    reviewer quotes must match the stored canonical hash. Anything else is
    refused; an approval can never authorise a different action.
    """
    if approval.status != "pending":
        raise ConflictError(
            f"This request was already {approval.status.replace('_', ' ')}.",
            details={"status": approval.status},
        )
    if is_expired(approval):
        approval.status = "expired"
        await session.flush()
        raise ApprovalExpired(
            "This approval request has expired.",
            details={"expires_at": approval.expires_at.isoformat()},
        )
    if arguments_hash != approval.canonical_arguments_hash:
        raise ApprovalMismatch(
            "The proposed action no longer matches the payload that was reviewed.",
            details={"approval_id": str(approval.id)},
        )

    status = {
        "approve": "approved",
        "reject": "rejected",
        "request_changes": "changes_requested",
    }[decision]
    approval.status = status
    approval.decision = decision
    approval.decided_by = reviewer_id
    approval.decided_at = datetime.now(UTC)
    approval.review_note = note
    await session.flush()
    return approval


async def mark_executed(session: AsyncSession, *, approval: ApprovalRequest) -> ApprovalRequest:
    """Mark an approved request as executed."""
    approval.status = "executed"
    await session.flush()
    return approval


async def revoke(
    session: AsyncSession, *, approval: ApprovalRequest, note: str | None = None
) -> ApprovalRequest:
    """Revoke a pending or approved request without executing it."""
    if approval.status in FINAL_STATUSES:
        raise ConflictError(
            f"This request was already {approval.status.replace('_', ' ')}.",
            details={"status": approval.status},
        )
    approval.status = "revoked"
    approval.decision = "reject"
    approval.decided_at = datetime.now(UTC)
    if note:
        approval.review_note = note
    await session.flush()
    return approval


def approval_read(approval: ApprovalRequest) -> dict[str, Any]:
    """Serialise an approval request for the API."""
    return {
        "id": approval.id,
        "workspace_id": approval.workspace_id,
        "run_id": approval.run_id,
        "agent_version_id": approval.agent_version_id,
        "tool_definition_id": approval.tool_definition_id,
        "tool_name": approval.tool_name,
        "risk_level": approval.risk_level,
        "canonical_arguments_hash": approval.canonical_arguments_hash,
        "arguments": approval.arguments,
        "requested_by": approval.requested_by,
        "status": approval.status,
        "decision": approval.decision,
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at,
        "review_note": approval.review_note,
        "policy_version": approval.policy_version,
        "expires_at": approval.expires_at,
        "created_at": approval.created_at,
        "is_expired": is_expired(approval),
    }


__all__ = [
    "FINAL_STATUSES",
    "approval_read",
    "create_approval_request",
    "decide",
    "get_approval",
    "is_expired",
    "list_approvals",
    "mark_executed",
    "revoke",
]
