"""Run history, event streaming, traces and cancellation."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.access import workspace_role
from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.errors import ResourceNotFound
from app.core.permissions import Permission
from app.db.session import get_session_factory
from app.models.runs import AgentRun, RunEvent
from app.schemas.common import Page
from app.schemas.runs import (
    RunCreateRequest,
    RunEventList,
    RunRead,
    TraceView,
)
from app.services import agents as agent_service
from app.services import audit as audit_service
from app.services import runs as run_service

router = APIRouter(prefix=f"{settings.api_prefix}/runs", tags=["runs"])


async def _authorized_run(
    session: AsyncSession,
    *,
    context: AuthContext,
    run_id: uuid.UUID,
    permission: Permission,
) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise ResourceNotFound("Run not found.")
    await workspace_role(
        session,
        context=context,
        workspace_id=run.workspace_id,
        permission=permission,
    )
    return run


@router.get("", response_model=Page[RunRead], summary="List runs")
async def list_runs(
    workspace_id: uuid.UUID = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
    agent_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[RunRead]:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.RUN_READ,
    )
    rows, total = await run_service.list_runs(
        session,
        workspace_id=workspace_id,
        status=status_filter,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    items = [
        RunRead(**run_service.run_read(run, agent_name=name, version_number=number))
        for run, name, number in rows
    ]
    return Page[RunRead](
        items=items,
        total=total,
        has_more=offset + len(items) < total,
    )


@router.post(
    "",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a run",
)
async def create_run(
    payload: RunCreateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> RunRead:
    agent = await agent_service.get_agent_by_id(session, agent_id=payload.agent_id)
    await workspace_role(
        session,
        context=context,
        workspace_id=agent.workspace_id,
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
    )
    await audit_service.record_event(
        session,
        action="run.queued",
        resource_type="agent_run",
        resource_id=str(run.id),
        workspace_id=agent.workspace_id,
        actor_id=context.actor_id,
        metadata={"agent_id": str(agent.id), "version_number": version.version_number},
    )
    await session.commit()
    run_service.schedule_execution(run.id)
    return RunRead(
        **run_service.run_read(run, agent_name=agent.name, version_number=version.version_number)
    )


@router.get("/{run_id}", response_model=RunRead, summary="Get a run")
async def get_run(
    run_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> RunRead:
    run = await _authorized_run(
        session, context=context, run_id=run_id, permission=Permission.RUN_READ
    )
    full, name, number = await run_service.get_run(
        session, workspace_id=run.workspace_id, run_id=run.id
    )
    return RunRead(**run_service.run_read(full, agent_name=name, version_number=number))


@router.get(
    "/{run_id}/events",
    response_model=RunEventList,
    summary="List persisted run events after a sequence number",
)
async def list_events(
    run_id: uuid.UUID,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> RunEventList:
    run = await _authorized_run(
        session, context=context, run_id=run_id, permission=Permission.RUN_READ
    )
    events, run_status, has_more = await run_service.get_events(
        session,
        workspace_id=run.workspace_id,
        run_id=run.id,
        after_seq=after_seq,
        limit=limit,
    )
    items = [run_service.event_read(event) for event in events]
    return RunEventList(
        items=items,
        last_sequence=events[-1].sequence_number if events else after_seq,
        run_status=run_status,
        has_more=has_more,
    )


@router.get(
    "/{run_id}/events/stream",
    summary="Stream run events as Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream_events(
    run_id: uuid.UUID,
    after_seq: int = Query(default=0, ge=0),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await _authorized_run(session, context=context, run_id=run_id, permission=Permission.RUN_READ)

    async def generate() -> AsyncIterator[str]:
        last = after_seq
        ticks = 0
        factory = get_session_factory()
        while ticks < 2400:  # hard stop after ~20 minutes
            ticks += 1
            async with factory() as poll:
                current = await poll.get(AgentRun, run_id)
                if current is None:
                    return
                rows = (
                    await poll.scalars(
                        select(RunEvent)
                        .where(
                            RunEvent.run_id == run_id,
                            RunEvent.sequence_number > last,
                        )
                        .order_by(RunEvent.sequence_number)
                        .limit(200)
                    )
                ).all()
                run_status = current.status

            for event in rows:
                last = event.sequence_number
                data = json.dumps(run_service.event_read(event), default=str)
                yield f"id: {last}\ndata: {data}\n\n"

            if run_status in run_service.TERMINAL_RUN_STATUSES and not rows:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/trace", response_model=TraceView, summary="Get a run trace")
async def get_trace(
    run_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> TraceView:
    run = await _authorized_run(
        session, context=context, run_id=run_id, permission=Permission.RUN_READ
    )
    spans = await run_service.get_spans(session, workspace_id=run.workspace_id, run_id=run.id)
    return TraceView(
        run_id=run.id,
        spans=[run_service.span_read(span) for span in spans],
    )


@router.post("/{run_id}/cancel", response_model=RunRead, summary="Cancel a run")
async def cancel_run(
    run_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> RunRead:
    run = await _authorized_run(
        session, context=context, run_id=run_id, permission=Permission.RUN_CANCEL
    )
    await run_service.request_cancel(session, run=run)
    await audit_service.record_event(
        session,
        action="run.cancel",
        resource_type="agent_run",
        resource_id=str(run.id),
        workspace_id=run.workspace_id,
        actor_id=context.actor_id,
        metadata={"status": run.status},
    )
    await session.commit()
    full, name, number = await run_service.get_run(
        session, workspace_id=run.workspace_id, run_id=run.id
    )
    return RunRead(**run_service.run_read(full, agent_name=name, version_number=number))


__all__ = ["router"]
