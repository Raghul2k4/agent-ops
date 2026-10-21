"""API serializers shared by the identity and workspace routers."""

from __future__ import annotations

from app.core.permissions import Role
from app.models.identity import Workspace
from app.schemas.identity import WorkspaceRead


def workspace_read(
    workspace: Workspace,
    role: Role,
    member_count: int | None = None,
) -> WorkspaceRead:
    """Project a workspace row plus the caller's role into the API shape."""
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        role=role,
        member_count=member_count,
        settings=workspace.settings or {},
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


__all__ = ["workspace_read"]
