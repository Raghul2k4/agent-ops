"""Run persistence, queries and cancellation.

The runtime engine owns execution; this module owns the rows the API reads.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ResourceNotFound
from app.models.agents import Agent, AgentVersion
from app.models.runs import AgentRun, RunEvent, TraceSpan
from app.runtime import cancellation
from app.schemas.agents import AgentConfiguration

TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

_tasks: set[asyncio.Task[None]] = set()


async def create_run(
    session: AsyncSession,
    *,
    agent: Agent,
    version: AgentVersion,
    actor_id: uuid.UUID | None,
    run_input: dict[str, Any],
    replay_of_run_id: uuid.UUID | None = None,
    replay_mode: bool = False,
) -> AgentRun:
    configuration = AgentConfiguration.model_validate(version.configuration)
    run = AgentRun(
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        agent_version_id=version.id,
        initiated_by=actor_id,
        status="queued",
        input=run_input,
        model_config_id=configuration.model_config_id,
        replay_of_run_id=replay_of_run_id,
        replay_mode=replay_mode,
    )
    session.add(run)
    await session.flush()
    return run


def schedule_execution(run_id: uuid.UUID) -> None:
    """Start execution in the background after the creating transaction commits."""
    from app.runtime.engine import execute_run

    task = asyncio.create_task(execute_run(run_id), name=f"agent-run-{run_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def schedule_resume(run_id: uuid.UUID, approval_id: uuid.UUID) -> None:
    """Continue a paused run in the background after the decision commits."""
    from app.runtime.engine import resume_run

    task = asyncio.create_task(resume_run(run_id, approval_id), name=f"agent-resume-{run_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def list_runs(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    status: str | None = None,
    agent_id: uuid.UUID | None = None,
    error_code: str | None = None,
    model_config_id: uuid.UUID | None = None,
    tool_name: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[tuple[AgentRun, str | None, int | None]], int]:
    conditions = [AgentRun.workspace_id == workspace_id]
    if status:
        conditions.append(AgentRun.status == status)
    if agent_id:
        conditions.append(AgentRun.agent_id == agent_id)
    if error_code:
        conditions.append(AgentRun.error_code == error_code)
    if model_config_id:
        conditions.append(AgentRun.model_config_id == model_config_id)
    if created_after:
        conditions.append(AgentRun.created_at >= created_after)
    if created_before:
        conditions.append(AgentRun.created_at <= created_before)
    if tool_name:
        # The tool filter reads the persisted event log, never the live run.
        conditions.append(
            AgentRun.id.in_(
                select(RunEvent.run_id).where(
                    RunEvent.event_type == "tool.request",
                    RunEvent.payload["tool"].astext == tool_name,
                )
            )
        )

    base = (
        select(AgentRun, Agent.name, AgentVersion.version_number)
        .join(Agent, AgentRun.agent_id == Agent.id)
        .join(AgentVersion, AgentRun.agent_version_id == AgentVersion.id)
        .where(*conditions)
    )
    total = int(
        await session.scalar(select(func.count()).select_from(AgentRun).where(*conditions)) or 0
    )
    rows = (
        await session.execute(base.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return [(run, name, number) for run, name, number in rows], total


async def get_run(
    session: AsyncSession, *, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[AgentRun, str | None, int | None]:
    row = (
        await session.execute(
            select(AgentRun, Agent.name, AgentVersion.version_number)
            .join(Agent, AgentRun.agent_id == Agent.id)
            .join(AgentVersion, AgentRun.agent_version_id == AgentVersion.id)
            .where(AgentRun.workspace_id == workspace_id, AgentRun.id == run_id)
        )
    ).first()
    if row is None:
        raise ResourceNotFound("Run not found.")
    return row[0], row[1], row[2]


async def get_events(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    after_seq: int = 0,
    limit: int = 500,
) -> tuple[list[RunEvent], str, bool]:
    run = await session.scalar(
        select(AgentRun).where(AgentRun.workspace_id == workspace_id, AgentRun.id == run_id)
    )
    if run is None:
        raise ResourceNotFound("Run not found.")
    rows = (
        await session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.sequence_number > after_seq)
            .order_by(RunEvent.sequence_number)
            .limit(limit + 1)
        )
    ).all()
    events = list(rows)
    has_more = len(events) > limit
    return events[:limit], run.status, has_more


async def get_spans(
    session: AsyncSession, *, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> list[TraceSpan]:
    exists = await session.scalar(
        select(AgentRun.id).where(AgentRun.workspace_id == workspace_id, AgentRun.id == run_id)
    )
    if exists is None:
        raise ResourceNotFound("Run not found.")
    rows = (
        await session.scalars(
            select(TraceSpan)
            .where(TraceSpan.run_id == run_id)
            .order_by(TraceSpan.started_at, TraceSpan.id)
        )
    ).all()
    return list(rows)


async def request_cancel(session: AsyncSession, *, run: AgentRun) -> AgentRun:
    if run.status in TERMINAL_RUN_STATUSES:
        raise ConflictError("This run has already finished.")
    cancellation.request_cancellation(run.id)
    run.status = "cancelled"
    run.completed_at = datetime.now(UTC)
    run.error_code = "RUN_CANCELLED"
    run.error_summary = "Cancelled by the user."
    run.pending_approval_id = None
    session.add(run)
    await session.flush()
    return run


def run_read(
    run: AgentRun,
    *,
    agent_name: str | None = None,
    version_number: int | None = None,
) -> dict[str, Any]:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "agent_id": run.agent_id,
        "agent_name": agent_name,
        "agent_version_id": run.agent_version_id,
        "version_number": version_number,
        "initiated_by": run.initiated_by,
        "status": run.status,
        "input": run.input,
        "output": run.output,
        "model_config_id": run.model_config_id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration_ms": run.duration_ms,
        "token_usage": run.token_usage,
        "estimated_cost": float(run.estimated_cost) if run.estimated_cost is not None else None,
        "error_code": run.error_code,
        "error_summary": run.error_summary,
        "replay_of_run_id": run.replay_of_run_id,
        "pending_approval_id": run.pending_approval_id,
        "replay_mode": bool(run.replay_mode),
        "created_at": run.created_at,
    }


def event_read(event: RunEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "sequence_number": event.sequence_number,
        "event_type": event.event_type,
        "event_status": event.event_status,
        "payload": event.payload,
        "occurred_at": event.occurred_at,
    }


def span_read(span: TraceSpan) -> dict[str, Any]:
    return {
        "id": span.id,
        "parent_span_id": span.parent_span_id,
        "span_type": span.span_type,
        "name": span.name,
        "status": span.status,
        "started_at": span.started_at,
        "ended_at": span.ended_at,
        "duration_ms": span.duration_ms,
        "attributes": span.attributes,
    }


__all__ = [
    "TERMINAL_RUN_STATUSES",
    "create_run",
    "event_read",
    "get_events",
    "get_run",
    "get_spans",
    "list_runs",
    "request_cancel",
    "run_read",
    "schedule_execution",
    "span_read",
]
