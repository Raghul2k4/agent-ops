"""Tool execution boundary: validation, permissions, approval, timeout.

Order matters and mirrors the specification (AGENTS.md sections 11 and 26):

1. resolve the tool from the server-side registry (never from model output)
2. authorise the caller against the tool's declared permissions
3. validate the proposed arguments with a strict Pydantic model
4. stop for approval when the tool changes a business record
5. execute under a bounded timeout
6. normalise every failure into a controlled error category
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.errors import AppError, InvalidToolArguments, PolicyViolation, ToolExecutionFailed
from app.core.logging import get_logger
from app.core.security import hash_payload
from app.tools.base import (
    ToolApprovalRequiredError,
    ToolContext,
    ToolSpec,
    registry,
)

logger = get_logger(__name__)

MAX_RESULT_BYTES = 256_000


@dataclass(slots=True)
class ToolExecution:
    """A successfully executed tool call."""

    tool_name: str
    tool_definition_id: Any
    risk_level: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    duration_ms: int
    tool_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


def _field_errors(exc: PydanticValidationError) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for error in exc.errors()[:10]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        errors.append(
            {
                "field": location or "arguments",
                "message": str(error.get("msg", "Invalid value")),
            }
        )
    return errors


def provider_tool_specs(specs: list[ToolSpec]) -> list[Any]:
    """Build provider-facing tool declarations from registry specs."""
    from app.providers.base import ToolSpec as ProviderToolSpec

    return [
        ProviderToolSpec(
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_schema(),
        )
        for spec in specs
    ]


async def execute_tool(
    context: ToolContext,
    *,
    tool_name: str,
    raw_arguments: dict[str, Any] | None,
) -> ToolExecution:
    """Validate and execute one tool call."""
    tool = registry.get(tool_name)
    if tool is None:
        raise InvalidToolArguments(
            "The requested tool is not registered in this workspace runtime.",
            details={"tool": tool_name},
        )

    spec = tool.spec
    missing = [
        permission.value
        for permission in spec.required_permissions
        if permission not in context.permissions
    ]
    if missing:
        raise PolicyViolation(
            "You do not have permission to use this tool.",
            details={"tool": tool_name, "missing_permissions": missing},
        )

    arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
    try:
        validated = spec.input_model.model_validate(arguments)
    except PydanticValidationError as exc:
        raise InvalidToolArguments(
            "The tool arguments did not match the tool contract.",
            details={"tool": tool_name, "fields": _field_errors(exc)},
        ) from exc

    canonical_arguments = validated.model_dump(mode="json")
    if spec.requires_approval:
        raise ToolApprovalRequiredError(
            tool_name=spec.name,
            arguments=canonical_arguments,
            canonical_hash=hash_payload({"tool": spec.name, "arguments": canonical_arguments}),
            risk_level=spec.risk_level,
            tool_definition_id=spec.definition_id,
        )

    started = time.perf_counter()
    try:
        async with asyncio.timeout(spec.timeout_seconds):
            result = await tool.execute(context, validated)
    except (LookupError, ValueError) as exc:
        raise ToolExecutionFailed(
            f"The tool '{spec.name}' could not find the requested data.",
            details={"tool": spec.name},
        ) from exc
    except TimeoutError as exc:
        raise ToolExecutionFailed(
            f"The tool '{spec.name}' timed out.",
            details={"tool": spec.name},
            retryable=True,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.exception("tool_execution_failed", extra={"tool": spec.name})
        raise ToolExecutionFailed(
            f"The tool '{spec.name}' failed.",
            details={"tool": spec.name},
        ) from exc

    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
    encoded = len(str(payload))
    if encoded > MAX_RESULT_BYTES:
        raise ToolExecutionFailed(
            f"The tool '{spec.name}' returned more data than the runtime accepts.",
            details={"tool": spec.name, "bytes": encoded},
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    return ToolExecution(
        tool_name=spec.name,
        tool_definition_id=spec.definition_id,
        risk_level=spec.risk_level,
        arguments=canonical_arguments,
        output=payload,
        duration_ms=duration_ms,
        tool_version=spec.version,
    )


__all__ = [
    "MAX_RESULT_BYTES",
    "ToolExecution",
    "execute_tool",
    "provider_tool_specs",
]
