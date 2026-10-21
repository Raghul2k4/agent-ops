"""Agent runtime engine.

One run walks a bounded model/tool loop:

* configuration comes from the immutable ``agent_versions`` snapshot
* budgets (steps, tool calls, wall clock, tokens, cost) are enforced here
* every model call and tool call produces a persisted event and trace span
* model-proposed tool names and arguments are validated by the tool executor
* cancellation is checked between every step and interrupts an in-flight call

Runs execute as background asyncio tasks in the API process for this milestone.
The engine only needs a session factory, so moving it behind a durable worker
later does not change the execution logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AppError,
    ExecutionLimitExceeded,
    InternalError,
    PolicyViolation,
    ProviderTimeout,
    ProviderUnavailable,
    ResourceNotFound,
    RunCancelled,
)
from app.core.logging import get_logger
from app.core.permissions import Permission, permissions_for_role
from app.core.security import hash_payload
from app.db.session import get_session_factory
from app.models.agents import AgentVersion
from app.models.providers import ModelConfig, ModelProvider
from app.models.runs import AgentRun, RunEvent, TraceSpan
from app.providers.base import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Provider,
    ProviderError,
    ProviderFailure,
)
from app.providers.factory import build_provider
from app.runtime import cancellation
from app.schemas.agents import AgentConfiguration
from app.services import agents as agent_service
from app.services import audit as audit_service
from app.services import tools as tool_service
from app.tools import ToolApprovalRequiredError, ToolContext, execute_tool, provider_tool_specs

logger = get_logger(__name__)

_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


@dataclass(slots=True)
class Usage:
    """Accumulated usage and estimated cost for one run."""

    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    cost: Decimal | None = Decimal("0")

    def add(self, usage: ModelUsage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    def priced(self, pricing: dict[str, Any], usage: ModelUsage) -> None:
        """Add the cost of one call when pricing metadata is available."""
        if self.cost is None:
            return
        input_rate = _decimal(pricing.get("input_per_million"))
        output_rate = _decimal(pricing.get("output_per_million"))
        if input_rate is None and output_rate is None:
            self.cost = None
            return
        self.cost += (
            Decimal(usage.input_tokens) * (input_rate or Decimal(0))
            + Decimal(usage.output_tokens) * (output_rate or Decimal(0))
        ) / Decimal(1_000_000)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
        }


@dataclass(slots=True)
class Outcome:
    status: str
    output: dict[str, Any] | None = None
    error_code: str | None = None
    error_summary: str | None = None
    usage: Usage = field(default_factory=Usage)


@dataclass(slots=True)
class RunLedger:
    """State of one run that must survive a bounded failure.

    ``executed_calls`` prevents an identical call from repeating a side
    effect, and ``completed_actions`` lets a run that hits a budget report
    what it actually did instead of an empty result.
    """

    executed_calls: dict[str, Any] = field(default_factory=dict)
    completed_actions: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _now() -> datetime:
    return datetime.now(UTC)


def _sanitize(
    value: Any,
    *,
    depth: int = 0,
    max_string: int = 1500,
    max_items: int = 20,
) -> Any:
    """Bound the size of payloads written to events and spans."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, str):
        if len(value) > max_string:
            return value[:max_string] + "...[truncated]"
        return value
    if isinstance(value, dict):
        return {
            str(key)[:100]: _sanitize(
                v, depth=depth + 1, max_string=max_string, max_items=max_items
            )
            for key, v in list(value.items())[:max_items]
        }
    if isinstance(value, (list, tuple)):
        items = [
            _sanitize(item, depth=depth + 1, max_string=max_string, max_items=max_items)
            for item in list(value)[:max_items]
        ]
        if len(value) > max_items:
            items.append(f"...[{len(value) - max_items} more]")
        return items
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    return value


async def _emit(
    session: AsyncSession,
    run: AgentRun,
    event_type: str,
    payload: dict[str, Any],
    status: str = "ok",
) -> None:
    latest = await session.scalar(
        select(func.coalesce(func.max(RunEvent.sequence_number), 0)).where(
            RunEvent.run_id == run.id
        )
    )
    session.add(
        RunEvent(
            workspace_id=run.workspace_id,
            run_id=run.id,
            sequence_number=int(latest or 0) + 1,
            event_type=event_type,
            event_status=status,
            payload=_sanitize(payload),
            occurred_at=_now(),
        )
    )
    await session.flush()


def _start_span(
    session: AsyncSession,
    run: AgentRun,
    *,
    span_type: str,
    name: str,
    parent_span_id: uuid.UUID | None,
    attributes: dict[str, Any] | None = None,
) -> TraceSpan:
    span = TraceSpan(
        workspace_id=run.workspace_id,
        run_id=run.id,
        parent_span_id=parent_span_id,
        span_type=span_type,
        name=name,
        status="running",
        started_at=_now(),
        attributes=_sanitize(attributes or {}),
    )
    session.add(span)
    return span


def _close_span(span: TraceSpan, *, status: str, duration_ms: int) -> None:
    span.status = status
    span.ended_at = _now()
    span.duration_ms = max(0, duration_ms)


def _check_cancel(cancel_event: asyncio.Event) -> None:
    if cancel_event.is_set():
        raise RunCancelled("The run was cancelled.")


def _check_budget(usage: Usage, config: AgentConfiguration, elapsed_seconds: float) -> float:
    """Raise when a budget is exhausted; return the wall-clock seconds left."""
    if usage.total_tokens >= config.limits.max_total_tokens:
        raise ExecutionLimitExceeded(
            "The run reached its token budget.",
            details={"max_total_tokens": config.limits.max_total_tokens},
        )
    if usage.cost is not None and usage.cost >= Decimal(str(config.limits.max_cost_usd)):
        raise ExecutionLimitExceeded(
            "The run reached its cost budget.",
            details={"max_cost_usd": config.limits.max_cost_usd},
        )
    remaining = config.limits.max_wall_clock_seconds - elapsed_seconds
    if remaining <= 0:
        raise ExecutionLimitExceeded(
            "The run reached its wall-clock limit.",
            details={"max_wall_clock_seconds": config.limits.max_wall_clock_seconds},
        )
    return remaining


def _map_provider_error(exc: ProviderError) -> AppError:
    if exc.failure == ProviderFailure.TIMEOUT:
        return ProviderTimeout("The model provider timed out.")
    if exc.failure == ProviderFailure.AUTHENTICATION:
        return ProviderUnavailable("The model provider rejected the configured credential.")
    if exc.failure == ProviderFailure.RATE_LIMITED:
        return ProviderUnavailable("The model provider is rate limiting requests.")
    return ProviderUnavailable("The model provider is unavailable.")


async def _chat_with_cancel(
    provider: Provider,
    request: ModelRequest,
    *,
    cancel_event: asyncio.Event,
    timeout_seconds: float,
) -> ModelResponse:
    """Race the provider call against cancellation and the wall-clock budget."""
    call = asyncio.create_task(provider.chat(request))
    cancelled = asyncio.create_task(cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {call, cancelled},
            timeout=max(0.1, timeout_seconds),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancelled in done and cancel_event.is_set():
            call.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await call
            raise RunCancelled("The run was cancelled.")
        if call in done:
            return await call
        call.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await call
        raise ProviderError(
            "The provider call timed out.",
            failure=ProviderFailure.TIMEOUT,
            retryable=True,
        )
    finally:
        cancelled.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await cancelled


async def _run_loop(
    session: AsyncSession,
    run: AgentRun,
    run_span: TraceSpan,
    cancel_event: asyncio.Event,
    started: float,
    usage: Usage,
    ledger: RunLedger,
) -> Outcome:
    version = await session.get(AgentVersion, run.agent_version_id)
    if version is None:
        raise ResourceNotFound("The agent version used by this run no longer exists.")
    config = AgentConfiguration.model_validate(version.configuration)

    provider_row = await session.get(ModelProvider, config.provider_id)
    if (
        provider_row is None
        or provider_row.workspace_id != run.workspace_id
        or provider_row.status == "disabled"
    ):
        raise PolicyViolation("The model provider configured for this agent is unavailable.")

    model_row = await session.get(ModelConfig, config.model_config_id)
    if model_row is None or model_row.workspace_id != run.workspace_id:
        raise PolicyViolation("The model configured for this agent no longer exists.")
    pricing = dict(model_row.pricing or {})

    tool_specs = await tool_service.resolve_tool_specs(session, run.workspace_id, config.tool_ids)
    try:
        role = await agent_service.member_role(
            session, workspace_id=run.workspace_id, profile_id=run.initiated_by
        )
    except ResourceNotFound as exc:
        raise PolicyViolation(
            "The user who started this run no longer has access to the workspace."
        ) from exc
    permissions: frozenset[Permission] = permissions_for_role(role)

    try:
        adapter = build_provider(provider_row, timeout_seconds=config.parameters.timeout_seconds)
    except ProviderError as exc:
        raise ProviderUnavailable(exc.message) from exc

    # Release the read transaction before the first external call.
    await session.commit()

    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=config.system_prompt),
        ChatMessage(role="user", content=str(run.input.get("message", ""))),
    ]
    tool_specs_for_model = provider_tool_specs(tool_specs)
    tool_calls_used = 0
    context = ToolContext(
        session=session,
        workspace_id=run.workspace_id,
        actor_id=run.initiated_by,
        run_id=run.id,
        permissions=permissions,
    )

    for step in range(1, config.limits.max_steps + 1):
        ledger.step = step
        _check_cancel(cancel_event)
        elapsed = time.monotonic() - started
        remaining = _check_budget(usage, config, elapsed)

        span = _start_span(
            session,
            run,
            span_type="model_call",
            name=config.model_name,
            parent_span_id=run_span.id,
            attributes={
                "step": step,
                "model": config.model_name,
                "provider": provider_row.provider_type,
            },
        )
        await _emit(
            session,
            run,
            "model.request",
            {
                "step": step,
                "model": config.model_name,
                "message_count": len(messages),
                "tool_count": len(tool_specs_for_model),
            },
            "info",
        )
        await session.commit()

        call_started = time.monotonic()
        request = ModelRequest(
            model=config.model_name,
            messages=messages,
            tools=tool_specs_for_model,
            temperature=config.parameters.temperature,
            max_output_tokens=config.parameters.max_output_tokens,
            top_p=config.parameters.top_p,
            timeout_seconds=min(float(config.parameters.timeout_seconds), remaining),
        )
        try:
            response = await _chat_with_cancel(
                adapter,
                request,
                cancel_event=cancel_event,
                timeout_seconds=min(float(config.parameters.timeout_seconds), remaining),
            )
        except ProviderError as exc:
            _close_span(
                span,
                status="error",
                duration_ms=int((time.monotonic() - call_started) * 1000),
            )
            logger.info("provider_call_failed", extra={"failure": exc.failure.value})
            raise _map_provider_error(exc) from exc
        except AppError:
            _close_span(
                span,
                status="error",
                duration_ms=int((time.monotonic() - call_started) * 1000),
            )
            raise

        duration_ms = int((time.monotonic() - call_started) * 1000)
        _close_span(span, status="ok", duration_ms=duration_ms)
        usage.add(response.usage)
        usage.model_calls += 1
        usage.priced(pricing, response.usage)

        await _emit(
            session,
            run,
            "model.response",
            {
                "step": step,
                "model": response.model or config.model_name,
                "finish_reason": response.finish_reason,
                "duration_ms": duration_ms,
                "usage": response.usage.model_dump(),
                "content_preview": (response.content or "")[:600] or None,
                "tool_calls": [{"id": call.id, "name": call.name} for call in response.tool_calls],
            },
        )

        _check_budget(usage, config, time.monotonic() - started)

        if not response.tool_calls:
            message = (response.content or "")[:32000]
            return Outcome(
                status="succeeded",
                output={
                    "message": message,
                    "finish_reason": response.finish_reason,
                    "steps": step,
                    "usage": usage.to_dict(),
                },
                usage=usage,
            )

        messages.append(
            ChatMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            )
        )

        for call in response.tool_calls:
            _check_cancel(cancel_event)
            tool_calls_used += 1
            if tool_calls_used > config.limits.max_tool_calls:
                raise ExecutionLimitExceeded(
                    "The run reached its tool-call budget.",
                    details={"max_tool_calls": config.limits.max_tool_calls},
                )

            call_key = hash_payload({"tool": call.name, "arguments": call.arguments})
            cached = ledger.executed_calls.get(call_key)
            if cached is not None:
                # The identical call already ran in this run. Reuse the recorded
                # result instead of repeating a possible side effect.
                await _emit(
                    session,
                    run,
                    "tool.cached",
                    {
                        "tool": call.name,
                        "arguments": call.arguments,
                        "note": (
                            "Reused the result of an identical call in this run; "
                            "the tool was not executed again."
                        ),
                    },
                    "info",
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=json.dumps(cached.output, default=str)[:16000],
                        tool_call_id=call.id,
                        tool_name=cached.tool_name,
                    )
                )
                await session.commit()
                continue

            await _emit(
                session,
                run,
                "tool.request",
                {"tool": call.name, "arguments": call.arguments},
                "info",
            )

            tool_span = _start_span(
                session,
                run,
                span_type="tool_call",
                name=call.name,
                parent_span_id=run_span.id,
                attributes={"tool": call.name, "arguments": call.arguments},
            )
            tool_started = time.monotonic()
            try:
                result = await execute_tool(
                    context, tool_name=call.name, raw_arguments=call.arguments
                )
            except ToolApprovalRequiredError as exc:
                _close_span(
                    tool_span,
                    status="cancelled",
                    duration_ms=int((time.monotonic() - tool_started) * 1000),
                )
                await _emit(
                    session,
                    run,
                    "approval.required",
                    {
                        "tool": exc.tool_name,
                        "risk_level": exc.risk_level,
                        "arguments": exc.arguments,
                        "canonical_arguments_hash": exc.canonical_hash,
                        "tool_definition_id": str(exc.tool_definition_id),
                        "note": (
                            "The action was not executed. Approvals are implemented in the "
                            "next milestone."
                        ),
                    },
                    "warning",
                )
                return Outcome(
                    status="awaiting_approval",
                    output={
                        "pending_approval": {
                            "tool": exc.tool_name,
                            "risk_level": exc.risk_level,
                            "arguments": _sanitize(exc.arguments),
                            "canonical_arguments_hash": exc.canonical_hash,
                        },
                        "message": None,
                    },
                    usage=usage,
                )
            except AppError as exc:
                # The executor was invoked but rejected or failed the call. It
                # still counts as an attempted tool execution for reporting.
                usage.tool_calls += 1
                _close_span(
                    tool_span,
                    status="error",
                    duration_ms=int((time.monotonic() - tool_started) * 1000),
                )
                await _emit(
                    session,
                    run,
                    "tool.error",
                    {"tool": call.name, "code": exc.code.value, "message": exc.message},
                    "error",
                )
                raise

            usage.tool_calls += 1
            tool_duration = int((time.monotonic() - tool_started) * 1000)
            _close_span(tool_span, status="ok", duration_ms=tool_duration)
            ledger.executed_calls[call_key] = result
            ledger.completed_actions.append(
                {
                    "tool": result.tool_name,
                    "risk_level": result.risk_level,
                    "arguments": _sanitize(result.arguments, max_string=500),
                    "output": _sanitize(result.output, max_string=2000, max_items=20),
                }
            )
            await _emit(
                session,
                run,
                "tool.result",
                {
                    "tool": result.tool_name,
                    "duration_ms": result.duration_ms,
                    "risk_level": result.risk_level,
                    "output": result.output,
                },
            )
            messages.append(
                ChatMessage(
                    role="tool",
                    content=json.dumps(result.output, default=str)[:16000],
                    tool_call_id=call.id,
                    tool_name=result.tool_name,
                )
            )
            # Persist the tool result and its event before the next iteration.
            await session.commit()

    raise ExecutionLimitExceeded(
        "The run reached its maximum number of steps.",
        details={"max_steps": config.limits.max_steps},
    )


def _partial_output(
    completed_actions: list[dict[str, Any]],
    *,
    step: int,
    usage: Usage,
    reason: str,
) -> dict[str, Any]:
    """Describe what a bounded run did before it was stopped.

    A run that hits a budget still performed work. Reporting the completed
    actions keeps the failure honest and actionable instead of returning an
    empty result.
    """
    return {
        "message": None,
        "steps": step,
        "stopped_because": reason,
        "completed_actions": completed_actions,
        "usage": usage.to_dict(),
    }


async def _finalize(
    session: AsyncSession,
    run: AgentRun,
    run_span: TraceSpan,
    outcome: Outcome,
    started: float,
) -> None:
    now = _now()
    run.status = outcome.status
    run.output = (
        _sanitize(outcome.output, max_string=32000, max_items=50) if outcome.output else None
    )
    run.token_usage = outcome.usage.to_dict()
    run.estimated_cost = outcome.usage.cost
    run.error_code = outcome.error_code
    run.error_summary = outcome.error_summary

    terminal = outcome.status in _TERMINAL
    if terminal:
        run.completed_at = now
        run.duration_ms = max(0, int((time.monotonic() - started) * 1000))
        run_span.ended_at = now
        run_span.duration_ms = run.duration_ms
        run_span.status = {
            "succeeded": "ok",
            "failed": "error",
            "cancelled": "cancelled",
        }.get(outcome.status, "error")
    else:
        run_span.status = "ok"
        run_span.ended_at = now
        run_span.duration_ms = max(0, int((time.monotonic() - started) * 1000))

    event_type = {
        "succeeded": "run.succeeded",
        "failed": "run.failed",
        "cancelled": "run.cancelled",
        "awaiting_approval": "run.awaiting_approval",
    }.get(outcome.status, "run.failed")
    event_status = (
        "ok"
        if outcome.status == "succeeded"
        else ("warning" if outcome.status == "awaiting_approval" else "error")
    )
    await _emit(
        session,
        run,
        event_type,
        {
            "status": outcome.status,
            "duration_ms": run.duration_ms,
            "usage": outcome.usage.to_dict(),
            "error_code": outcome.error_code,
            "error_summary": outcome.error_summary,
        },
        event_status,
    )

    if outcome.status != "awaiting_approval":
        await audit_service.record_event(
            session,
            action=f"run.{outcome.status}",
            resource_type="agent_run",
            resource_id=str(run.id),
            workspace_id=run.workspace_id,
            actor_id=run.initiated_by,
            outcome="success" if outcome.status == "succeeded" else "failure",
            metadata={
                "agent_id": str(run.agent_id),
                "version_id": str(run.agent_version_id),
                "error_code": outcome.error_code,
                "duration_ms": run.duration_ms,
            },
        )

    await session.commit()


async def execute_run(run_id: uuid.UUID) -> None:
    """Execute one queued run. Safe to call as a background task."""
    cancel_event = cancellation.register(run_id)
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            run = await session.get(AgentRun, run_id)
            if run is None or run.status != "queued":
                return

            started = time.monotonic()
            run.status = "running"
            run.started_at = _now()
            run_span = _start_span(
                session,
                run,
                span_type="agent_run",
                name=f"agent:{run.agent_id}",
                parent_span_id=None,
                attributes={"agent_id": str(run.agent_id)},
            )
            await session.flush()
            await _emit(
                session,
                run,
                "run.started",
                {
                    "agent_id": str(run.agent_id),
                    "agent_version_id": str(run.agent_version_id),
                },
                "info",
            )
            await session.commit()

            usage = Usage()
            ledger = RunLedger()
            try:
                outcome = await _run_loop(
                    session, run, run_span, cancel_event, started, usage, ledger
                )
            except RunCancelled:
                outcome = Outcome(
                    status="cancelled",
                    error_code="RUN_CANCELLED",
                    error_summary="The run was cancelled.",
                    usage=usage,
                )
            except ProviderError as exc:
                outcome = Outcome(
                    status="failed",
                    error_code="PROVIDER_UNAVAILABLE",
                    error_summary=_map_provider_error(exc).message,
                    usage=usage,
                )
            except ExecutionLimitExceeded as exc:
                # A bounded run still performed work. Report what it did so the
                # failure is actionable instead of an empty result.
                outcome = Outcome(
                    status="failed",
                    error_code=exc.code.value,
                    error_summary=exc.message,
                    output=_partial_output(
                        ledger.completed_actions,
                        step=ledger.step,
                        usage=usage,
                        reason=exc.message,
                    ),
                    usage=usage,
                )
            except AppError as exc:
                outcome = Outcome(
                    status="failed",
                    error_code=exc.code.value,
                    error_summary=exc.message,
                    usage=usage,
                )
            except Exception:
                logger.exception("run_execution_crashed", extra={"run_id": str(run_id)})
                outcome = Outcome(
                    status="failed",
                    error_code=InternalError.code.value,
                    error_summary="The run failed because of an internal error.",
                    usage=usage,
                )

            await _finalize(session, run, run_span, outcome, started)
    except Exception:
        logger.exception("run_worker_crashed", extra={"run_id": str(run_id)})
    finally:
        cancellation.clear(run_id)


__all__ = ["Usage", "execute_run"]
