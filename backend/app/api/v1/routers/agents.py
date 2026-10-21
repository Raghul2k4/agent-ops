"""Agent Studio endpoints: CRUD, draft, versions, publish and runs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.access import agent_permission, workspace_role
from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.api.v1.serializers import agent_read, agent_version_read
from app.core.config import settings
from app.core.permissions import Permission
from app.models.agents import AgentVersion
from app.schemas.agents import (
    AgentCreateRequest,
    AgentDuplicateRequest,
    AgentPublishRequest,
    AgentRead,
    AgentRollbackRequest,
    AgentRunRequest,
    AgentTemplateRead,
    AgentUpdateRequest,
    AgentVersionRead,
)
from app.schemas.runs import RunRead
from app.services import agents as agent_service
from app.services import audit as audit_service
from app.services import runs as run_service

router = APIRouter(prefix=f"{settings.api_prefix}/agents", tags=["agents"])


async def _version_number(session: AsyncSession, agent_version_id: uuid.UUID | None) -> int | None:
    if agent_version_id is None:
        return None
    return await session.scalar(
        select(AgentVersion.version_number).where(AgentVersion.id == agent_version_id)
    )


@router.get("/templates", response_model=list[AgentTemplateRead], summary="List agent templates")
async def list_templates(
    context: AuthContext = Depends(get_auth_context),
) -> list[AgentTemplateRead]:
    """Return the built-in, functional agent templates."""
    _ = context
    return [
        AgentTemplateRead(**agent_service.template_read(template))
        for template in agent_service.AGENT_TEMPLATES
    ]


@router.get("", response_model=list[AgentRead], summary="List agents")
async def list_agents(
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[AgentRead]:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.AGENT_READ,
    )
    agents = await agent_service.list_agents(session, workspace_id=workspace_id)
    numbers = await agent_service.current_version_numbers(session, agents)
    return [
        agent_read(
            agent,
            (
                numbers.get(agent.current_published_version_id)
                if agent.current_published_version_id
                else None
            ),
        )
        for agent in agents
    ]


@router.post(
    "",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent",
)
async def create_agent(
    payload: AgentCreateRequest,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentRead:
    role = await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.AGENT_WRITE,
    )
    agent = await agent_service.create_agent(
        session,
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        payload=payload,
    )
    await audit_service.record_event(
        session,
        action="agent.create",
        resource_type="agent",
        resource_id=str(agent.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={
            "name": agent.name,
            "template_key": payload.template_key,
            "role": role.value,
        },
    )
    await session.commit()
    return agent_read(agent)


@router.get("/{agent_id}", response_model=AgentRead, summary="Get an agent")
async def get_agent(
    agent_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_READ,
    )
    number = await _version_number(session, agent.current_published_version_id)
    return agent_read(agent, number)


@router.patch("/{agent_id}", response_model=AgentRead, summary="Update an agent draft")
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_WRITE,
    )
    await agent_service.update_agent(session, agent=agent, payload=payload)
    await audit_service.record_event(
        session,
        action="agent.update",
        resource_type="agent",
        resource_id=str(agent.id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={
            "name": agent.name,
            "draft_changed": payload.draft_configuration is not None,
            "note": payload.change_note,
        },
    )
    await session.commit()
    await session.refresh(agent)
    number = await _version_number(session, agent.current_published_version_id)
    return agent_read(agent, number)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an agent")
async def delete_agent(
    agent_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Response:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_WRITE,
    )
    await agent_service.delete_agent(session, agent=agent)
    await audit_service.record_event(
        session,
        action="agent.delete",
        resource_type="agent",
        resource_id=str(agent_id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={"name": agent.name},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{agent_id}/archive", response_model=AgentRead, summary="Archive an agent")
async def archive_agent(
    agent_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_WRITE,
    )
    await agent_service.archive_agent(session, agent=agent)
    await audit_service.record_event(
        session,
        action="agent.archive",
        resource_type="agent",
        resource_id=str(agent.id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={"name": agent.name},
    )
    await session.commit()
    return agent_read(agent, await _version_number(session, agent.current_published_version_id))


@router.get(
    "/{agent_id}/versions",
    response_model=list[AgentVersionRead],
    summary="List immutable agent versions",
)
async def list_versions(
    agent_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[AgentVersionRead]:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_READ,
    )
    versions = await agent_service.list_versions(session, agent_id=agent.id)
    return [agent_version_read(version) for version in versions]


@router.post(
    "/{agent_id}/publish",
    response_model=AgentVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Publish the current draft as an immutable version",
)
async def publish_agent(
    agent_id: uuid.UUID,
    payload: AgentPublishRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentVersionRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_PUBLISH,
    )
    version = await agent_service.publish_agent(
        session,
        agent=agent,
        actor_id=context.actor_id,
        change_summary=payload.change_summary,
    )
    await audit_service.record_event(
        session,
        action="agent.publish",
        resource_type="agent_version",
        resource_id=str(version.id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={
            "agent_id": str(agent.id),
            "version_number": version.version_number,
            "configuration_hash": version.configuration_hash,
        },
    )
    await session.commit()
    return agent_version_read(version)


@router.post(
    "/{agent_id}/rollback",
    response_model=AgentVersionRead,
    summary="Roll the published pointer back to a prior version",
)
async def rollback_agent(
    agent_id: uuid.UUID,
    payload: AgentRollbackRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentVersionRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_PUBLISH,
    )
    version = await agent_service.rollback_agent(
        session, agent=agent, version_id=payload.version_id
    )
    await audit_service.record_event(
        session,
        action="agent.rollback",
        resource_type="agent_version",
        resource_id=str(version.id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={"agent_id": str(agent.id), "version_number": version.version_number},
    )
    await session.commit()
    return agent_version_read(version)


@router.post(
    "/{agent_id}/duplicate",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate an agent draft",
)
async def duplicate_agent(
    agent_id: uuid.UUID,
    payload: AgentDuplicateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> AgentRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.AGENT_WRITE,
    )
    duplicate = await agent_service.duplicate_agent(
        session, agent=agent, actor_id=context.actor_id, name=payload.name
    )
    await audit_service.record_event(
        session,
        action="agent.duplicate",
        resource_type="agent",
        resource_id=str(duplicate.id),
        workspace_id=duplicate.workspace_id,
        actor_id=context.actor_id,
        metadata={"source_agent_id": str(agent.id), "name": duplicate.name},
    )
    await session.commit()
    return agent_read(duplicate)


@router.post(
    "/{agent_id}/run",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a run against an agent version",
)
async def run_agent(
    agent_id: uuid.UUID,
    payload: AgentRunRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> RunRead:
    agent, _role = await agent_permission(
        session,
        context=context,
        agent_id=agent_id,
        permission=Permission.RUN_EXECUTE,
    )
    version = await agent_service.resolve_version(
        session, agent=agent, version_id=payload.version_id
    )
    run = await run_service.create_run(
        session,
        agent=agent,
        version=version,
        actor_id=context.actor_id,
        run_input=payload.input,
        replay_of_run_id=payload.replay_of_run_id,
    )
    await audit_service.record_event(
        session,
        action="run.queued",
        resource_type="agent_run",
        resource_id=str(run.id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={
            "agent_id": str(agent.id),
            "version_number": version.version_number,
        },
    )
    await session.commit()
    run_service.schedule_execution(run.id)
    return RunRead(
        **run_service.run_read(run, agent_name=agent.name, version_number=version.version_number)
    )


# `/test` is the playground alias for a normal run. Both execute the published
# version through the same runtime; a draft must be published first so every run
# stays traceable to an immutable snapshot.
router.add_api_route(
    "/{agent_id}/test",
    run_agent,
    methods=["POST"],
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Test an agent (alias of run)",
    name="test_agent",
)


__all__ = ["router"]
