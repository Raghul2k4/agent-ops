"""Approval queue and decisions.

A reviewer sees exactly what the model proposed: the tool, the canonical
arguments, their hash and the risk level. The decision is bound to that hash,
so approving a request can never authorise a different action.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.access import workspace_role
from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.errors import ResourceNotFound
from app.core.permissions import Permission
from app.models.policies import ApprovalRequest
from app.models.runs import AgentRun
from app.schemas.common import Page
from app.schemas.policies import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalRead,
)
from app.services import approvals as approval_service
from app.services import audit as audit_service
from app.services import runs as run_service

router = APIRouter(prefix=f"{settings.api_prefix}/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalRead], summary="List approval requests")
async def list_approvals(
    workspace_id: uuid.UUID = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
    run_id: uuid.UUID | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[ApprovalRead]:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.APPROVAL_READ,
    )
    rows, total = await approval_service.list_approvals(
        session,
        workspace_id=workspace_id,
        status=status_filter,
        run_id=run_id,
        tool_name=tool_name,
        limit=limit,
        offset=offset,
    )
    items = [ApprovalRead(**approval_service.approval_read(row)) for row in rows]
    return Page[ApprovalRead](items=items, total=total, has_more=offset + len(items) < total)


@router.get("/{approval_id}", response_model=ApprovalRead, summary="Get an approval request")
async def get_approval(
    approval_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ApprovalRead:
    approval = await session.get(ApprovalRequest, approval_id)
    if approval is None:
        raise ResourceNotFound("Approval request not found.")
    await workspace_role(
        session,
        context=context,
        workspace_id=approval.workspace_id,
        permission=Permission.APPROVAL_READ,
    )
    return ApprovalRead(**approval_service.approval_read(approval))


@router.post(
    "/{approval_id}/decision",
    response_model=ApprovalDecisionResponse,
    summary="Approve, reject or request changes",
)
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ApprovalDecisionResponse:
    approval = await session.get(ApprovalRequest, approval_id)
    if approval is None:
        raise ResourceNotFound("Approval request not found.")
    await workspace_role(
        session,
        context=context,
        workspace_id=approval.workspace_id,
        permission=Permission.APPROVAL_DECIDE,
    )

    await approval_service.decide(
        session,
        approval=approval,
        decision=payload.decision,
        reviewer_id=context.actor_id,
        note=payload.note,
        arguments_hash=payload.arguments_hash,
    )
    await audit_service.record_event(
        session,
        action=f"approval.{payload.decision}",
        resource_type="approval_request",
        resource_id=str(approval.id),
        workspace_id=approval.workspace_id,
        actor_id=context.actor_id,
        outcome="success" if payload.decision == "approve" else "denied",
        metadata={
            "run_id": str(approval.run_id),
            "tool": approval.tool_name,
            "risk_level": approval.risk_level,
            "canonical_arguments_hash": approval.canonical_arguments_hash,
            "policy_version": approval.policy_version,
        },
    )

    message = "The approval was recorded."
    if payload.decision == "approve":
        # The run continues in the background; the action is re-validated
        # against the current policy immediately before it executes.
        await session.commit()
        run_service.schedule_resume(approval.run_id, approval.id)
        message = "Approved. The run continues and the approved action will execute."
    else:
        run = await session.get(AgentRun, approval.run_id)
        if run is not None and run.status == "awaiting_approval":
            from app.runtime.engine import fail_paused_run

            await fail_paused_run(
                session,
                run=run,
                error_code="APPROVAL_REJECTED",
                error_summary=(
                    "A reviewer rejected the proposed action."
                    if payload.decision == "reject"
                    else "A reviewer asked for changes; the run ended without acting."
                ),
            )
        else:
            await session.commit()
        message = (
            "The action was rejected and the run ended."
            if payload.decision == "reject"
            else "Changes were requested and the run ended without acting."
        )

    run = await session.get(AgentRun, approval.run_id)
    return ApprovalDecisionResponse(
        approval=ApprovalRead(**approval_service.approval_read(approval)),
        run_status=run.status if run is not None else "unknown",
        run_id=approval.run_id,
        message=message,
    )


@router.post(
    "/{approval_id}/revoke",
    response_model=ApprovalRead,
    status_code=status.HTTP_200_OK,
    summary="Revoke a pending request",
)
async def revoke_approval(
    approval_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ApprovalRead:
    approval = await session.get(ApprovalRequest, approval_id)
    if approval is None:
        raise ResourceNotFound("Approval request not found.")
    await workspace_role(
        session,
        context=context,
        workspace_id=approval.workspace_id,
        permission=Permission.WORKSPACE_UPDATE,
    )
    await approval_service.revoke(session, approval=approval, note="Revoked by an administrator.")
    await audit_service.record_event(
        session,
        action="approval.revoked",
        resource_type="approval_request",
        resource_id=str(approval.id),
        workspace_id=approval.workspace_id,
        actor_id=context.actor_id,
        outcome="denied",
        metadata={"run_id": str(approval.run_id), "tool": approval.tool_name},
    )
    await session.commit()
    await session.refresh(approval)
    return ApprovalRead(**approval_service.approval_read(approval))


__all__ = ["router"]
