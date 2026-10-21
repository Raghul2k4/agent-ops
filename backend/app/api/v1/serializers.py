"""API serializers shared by the identity and workspace routers."""

from __future__ import annotations

from app.core.permissions import Role
from app.models.agents import Agent, AgentVersion
from app.models.identity import Workspace
from app.schemas.agents import AgentRead, AgentVersionRead
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


def agent_read(agent: Agent, version_number: int | None = None) -> AgentRead:
    """Project an agent row, including its editable draft, into the API shape."""
    return AgentRead(
        id=agent.id,
        workspace_id=agent.workspace_id,
        name=agent.name,
        description=agent.description,
        status=agent.status,
        draft_configuration=agent.draft_configuration or {},
        current_published_version_id=agent.current_published_version_id,
        current_version_number=version_number,
        created_by=agent.created_by,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def agent_version_read(version: AgentVersion) -> AgentVersionRead:
    return AgentVersionRead(
        id=version.id,
        workspace_id=version.workspace_id,
        agent_id=version.agent_id,
        version_number=version.version_number,
        configuration=version.configuration,
        configuration_hash=version.configuration_hash,
        change_summary=version.change_summary,
        created_by=version.created_by,
        created_at=version.created_at,
    )


__all__ = ["agent_read", "agent_version_read", "workspace_read"]
