"""Workspace policy endpoints.

The policy document is the workspace's enforcement surface. Only an owner or
administrator may change it, and every change is versioned and audited.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.access import workspace_role
from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.permissions import Permission
from app.schemas.policies import PolicyRead, PolicyUpdateRequest
from app.services import audit as audit_service
from app.services import policies as policy_service

router = APIRouter(prefix=f"{settings.api_prefix}/policies", tags=["policies"])


@router.get("", response_model=PolicyRead, summary="Read the workspace policy")
async def read_policy(
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> PolicyRead:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.WORKSPACE_READ,
    )
    row = await policy_service.get_policy_row(session, workspace_id=workspace_id)
    await session.commit()
    return PolicyRead(**policy_service.policy_read(row))


@router.patch("", response_model=PolicyRead, summary="Update the workspace policy")
async def update_policy(
    payload: PolicyUpdateRequest,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> PolicyRead:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.WORKSPACE_UPDATE,
    )
    row = await policy_service.update_policy(
        session,
        workspace_id=workspace_id,
        payload=payload,
        actor_id=context.actor_id,
    )
    await audit_service.record_event(
        session,
        action="policy.update",
        resource_type="workspace_policy",
        resource_id=str(workspace_id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={
            "policy_version": row.version,
            "execution_paused": bool(row.execution_paused),
            "change_note": payload.change_note,
        },
    )
    await session.commit()
    await session.refresh(row)
    return PolicyRead(**policy_service.policy_read(row))


__all__ = ["router"]
