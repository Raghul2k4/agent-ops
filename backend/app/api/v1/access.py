"""Shared authorization helpers for workspace-scoped routers.

The role used for authorization is always resolved from the caller's active
membership in *that* workspace. ``AuthContext.permissions`` is a union across
all workspaces and must not be used for a workspace-scoped mutation.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext
from app.core.errors import PermissionDenied
from app.core.permissions import Permission, Role, role_has_permission
from app.models.agents import Agent
from app.models.identity import Profile
from app.services import agents as agent_service


def require_identity(context: AuthContext) -> Profile:
    """Agent Studio endpoints need a user identity, not an API key."""
    if context.profile is None:
        raise PermissionDenied(
            "This endpoint requires a signed-in user; API keys are not supported here."
        )
    return context.profile


async def workspace_role(
    session: AsyncSession,
    *,
    context: AuthContext,
    workspace_id: uuid.UUID,
    permission: Permission,
) -> Role:
    """Resolve the caller's role and require a permission in this workspace."""
    profile = require_identity(context)
    role = await agent_service.member_role(
        session, workspace_id=workspace_id, profile_id=profile.id
    )
    if not role_has_permission(role, permission):
        raise PermissionDenied(
            f"This action requires the '{permission.value}' permission in this workspace."
        )
    return role


async def agent_permission(
    session: AsyncSession,
    *,
    context: AuthContext,
    agent_id: uuid.UUID,
    permission: Permission,
) -> tuple[Agent, Role]:
    """Fetch an agent and authorize against its workspace membership.

    A non-member receives ``RESOURCE_NOT_FOUND`` from ``member_role`` so agent
    existence is not leaked across tenants.
    """
    agent = await agent_service.get_agent_by_id(session, agent_id=agent_id)
    role = await workspace_role(
        session,
        context=context,
        workspace_id=agent.workspace_id,
        permission=permission,
    )
    return agent, role


__all__ = ["agent_permission", "require_identity", "workspace_role"]
