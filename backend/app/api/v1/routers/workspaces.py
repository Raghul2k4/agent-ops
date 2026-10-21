"""Workspace and membership endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import (
    AuthContext,
    get_auth_context,
    get_db,
    require_workspace_scope,
)
from app.api.v1.serializers import workspace_read
from app.core.config import settings
from app.core.errors import PermissionDenied, ResourceNotFound
from app.core.logging import get_logger
from app.core.permissions import Permission, Role, role_has_permission
from app.models.identity import Profile, WorkspaceMember
from app.schemas.identity import (
    MemberInviteRequest,
    MemberRead,
    MemberRoleUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceRead,
    WorkspaceUpdateRequest,
)
from app.services import audit as audit_service
from app.services import workspaces as workspace_service

logger = get_logger(__name__)

router = APIRouter(prefix=settings.api_prefix, tags=["workspaces"])

_REQUIRES_IDENTITY = "This endpoint requires a user identity; API keys are not supported here."


def _require_profile(context: AuthContext) -> Profile:
    """Reject API-key callers from user-scoped workspace endpoints."""
    if context.profile is None:
        raise PermissionDenied(_REQUIRES_IDENTITY)
    return context.profile


def _require_workspace_permission(role, permission: Permission) -> None:  # type: ignore[no-untyped-def]
    """Authorize against the caller's role *in this workspace*.

    ``AuthContext.permissions`` is the union across every workspace the user
    belongs to, so it must never be used to authorize a workspace-scoped
    mutation: an owner of workspace A would otherwise be able to edit
    workspace B where they are only a viewer.
    """
    if not role_has_permission(role, permission):
        raise PermissionDenied(
            f"This action requires the '{permission.value}' permission in this workspace."
        )


@router.get("/workspaces", response_model=list[WorkspaceRead], summary="List my workspaces")
async def list_workspaces(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[WorkspaceRead]:
    """List the workspaces the caller belongs to."""
    profile = _require_profile(context)
    memberships = await workspace_service.list_workspaces_for_user(session, profile=profile)
    counts = await workspace_service.member_counts(session, [ws.id for ws, _ in memberships])
    return [workspace_read(ws, role, counts.get(ws.id)) for ws, role in memberships]


@router.post(
    "/workspaces",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> WorkspaceRead:
    """Create a workspace owned by the caller."""
    profile = _require_profile(context)
    workspace, membership = await workspace_service.create_workspace(
        session, owner=profile, name=payload.name
    )
    await audit_service.record_event(
        session,
        action="workspace.create",
        resource_type="workspace",
        resource_id=str(workspace.id),
        workspace_id=workspace.id,
        actor_id=profile.id,
        outcome="success",
        metadata={"name": workspace.name},
    )
    await session.commit()
    return workspace_read(workspace, Role(membership.role), 1)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceRead, summary="Get a workspace")
async def get_workspace(
    workspace_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> WorkspaceRead:
    """Fetch a single workspace the caller is a member of."""
    require_workspace_scope(context, workspace_id)
    profile = _require_profile(context)
    workspace, role = await workspace_service.get_workspace_for_member(
        session, workspace_id=workspace_id, profile=profile
    )
    counts = await workspace_service.member_counts(session, [workspace.id])
    return workspace_read(workspace, role, counts.get(workspace.id))


@router.patch(
    "/workspaces/{workspace_id}", response_model=WorkspaceRead, summary="Update a workspace"
)
async def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> WorkspaceRead:
    """Update workspace metadata. Requires `workspace.update`."""
    require_workspace_scope(context, workspace_id)
    profile = _require_profile(context)
    workspace, role = await workspace_service.get_workspace_for_member(
        session, workspace_id=workspace_id, profile=profile
    )
    _require_workspace_permission(role, Permission.WORKSPACE_UPDATE)
    if payload.name is not None:
        workspace.name = payload.name.strip()
    if payload.settings is not None:
        workspace.settings = payload.settings
    session.add(workspace)
    await audit_service.record_event(
        session,
        action="workspace.update",
        resource_type="workspace",
        resource_id=str(workspace.id),
        workspace_id=workspace.id,
        actor_id=profile.id,
        outcome="success",
    )
    await session.commit()
    return workspace_read(workspace, role)


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=list[MemberRead],
    summary="List workspace members",
)
async def list_members(
    workspace_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[MemberRead]:
    """List the members of a workspace."""
    require_workspace_scope(context, workspace_id)
    profile = _require_profile(context)
    await workspace_service.get_workspace_for_member(
        session, workspace_id=workspace_id, profile=profile
    )
    members = await workspace_service.list_members(session, workspace_id=workspace_id)
    return [
        MemberRead(
            id=member.id,
            user_id=member.user_id,
            email=member_profile.email,
            display_name=member_profile.display_name,
            role=member.role,
            status=member.status,
            created_at=member.created_at,
        )
        for member, member_profile in members
    ]


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a workspace member",
)
async def add_member(
    workspace_id: uuid.UUID,
    payload: MemberInviteRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Add an existing user to the workspace."""
    require_workspace_scope(context, workspace_id)
    profile = _require_profile(context)
    workspace, role = await workspace_service.get_workspace_for_member(
        session, workspace_id=workspace_id, profile=profile
    )
    _require_workspace_permission(role, Permission.WORKSPACE_MANAGE_MEMBERS)
    member = await workspace_service.add_member(
        session,
        workspace=workspace,
        email=payload.email,
        role=payload.role,
        invited_by=profile.id,
    )
    await audit_service.record_event(
        session,
        action="workspace.member_added",
        resource_type="workspace_member",
        resource_id=str(member.id),
        workspace_id=workspace.id,
        actor_id=profile.id,
        outcome="success",
        metadata={"role": member.role},
    )
    await session.commit()
    added_profile = await session.get(Profile, member.user_id)
    return MemberRead(
        id=member.id,
        user_id=member.user_id,
        email=added_profile.email if added_profile else "",
        display_name=added_profile.display_name if added_profile else "",
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


@router.patch(
    "/workspaces/{workspace_id}/members/{member_id}",
    response_model=MemberRead,
    summary="Change a member role",
)
async def update_member_role(
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberRoleUpdateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Change the role of a workspace member."""
    require_workspace_scope(context, workspace_id)
    profile = _require_profile(context)
    workspace, role = await workspace_service.get_workspace_for_member(
        session, workspace_id=workspace_id, profile=profile
    )
    _require_workspace_permission(role, Permission.WORKSPACE_MANAGE_MEMBERS)
    member = await session.get(WorkspaceMember, member_id)
    if member is None or member.workspace_id != workspace.id:
        raise ResourceNotFound("Workspace member not found.")
    await workspace_service.change_member_role(session, member=member, role=payload.role)
    await audit_service.record_event(
        session,
        action="workspace.member_role_changed",
        resource_type="workspace_member",
        resource_id=str(member.id),
        workspace_id=workspace.id,
        actor_id=profile.id,
        outcome="success",
        metadata={"role": member.role},
    )
    await session.commit()
    member_profile = await session.get(Profile, member.user_id)
    return MemberRead(
        id=member.id,
        user_id=member.user_id,
        email=member_profile.email if member_profile else "",
        display_name=member_profile.display_name if member_profile else "",
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


@router.delete(
    "/workspaces/{workspace_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a workspace member",
)
async def remove_member(
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a member from the workspace."""
    require_workspace_scope(context, workspace_id)
    profile = _require_profile(context)
    workspace, role = await workspace_service.get_workspace_for_member(
        session, workspace_id=workspace_id, profile=profile
    )
    _require_workspace_permission(role, Permission.WORKSPACE_MANAGE_MEMBERS)
    member = await session.get(WorkspaceMember, member_id)
    if member is None or member.workspace_id != workspace.id:
        raise ResourceNotFound("Workspace member not found.")
    await workspace_service.remove_member(session, member=member)
    await audit_service.record_event(
        session,
        action="workspace.member_removed",
        resource_type="workspace_member",
        resource_id=str(member_id),
        workspace_id=workspace.id,
        actor_id=profile.id,
        outcome="success",
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
