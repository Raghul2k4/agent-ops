"""Tool registry persistence.

The executable definitions live in Python (``app.tools``). This service mirrors
them into ``app.tool_definitions`` so the UI, agents and run snapshots can
reference stable tool ids. The mirror is descriptive only - a database row can
never introduce an implementation.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PolicyViolation, ResourceNotFound
from app.models.tools import ToolDefinition
from app.tools import registry
from app.tools.base import ToolSpec


async def ensure_builtin_definitions(session: AsyncSession) -> list[ToolDefinition]:
    """Upsert the global built-in tool rows; safe to call repeatedly."""
    specs = registry.specs()
    ids = [spec.definition_id for spec in specs]
    rows = {
        row.id: row
        for row in (
            await session.scalars(select(ToolDefinition).where(ToolDefinition.id.in_(ids)))
        ).all()
    }

    definitions: list[ToolDefinition] = []
    for spec in specs:
        row = rows.get(spec.definition_id)
        if row is None:
            row = ToolDefinition(
                id=spec.definition_id,
                workspace_id=None,
                name=spec.name,
                version=spec.version,
                description=spec.description,
                input_schema=spec.input_schema(),
                output_schema=spec.output_schema(),
                risk_level=spec.risk_level,
                required_permissions=[permission.value for permission in spec.required_permissions],
                requires_approval=spec.requires_approval,
                timeout_seconds=spec.timeout_seconds,
                max_retries=spec.max_retries,
                idempotent=spec.idempotent,
                implementation=spec.implementation,
                enabled=True,
            )
            session.add(row)
        else:
            # Keep the descriptive contract in sync with the code, but never
            # touch executable behaviour (there is none in the row).
            row.description = spec.description
            row.input_schema = spec.input_schema()
            row.output_schema = spec.output_schema()
            row.risk_level = spec.risk_level
            row.required_permissions = [
                permission.value for permission in spec.required_permissions
            ]
            row.requires_approval = spec.requires_approval
            row.timeout_seconds = spec.timeout_seconds
            row.idempotent = spec.idempotent
        definitions.append(row)

    await session.flush()
    return definitions


async def list_tool_definitions(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[ToolDefinition]:
    """Return global built-ins plus any workspace-scoped tools."""
    await ensure_builtin_definitions(session)
    rows = (
        await session.scalars(
            select(ToolDefinition)
            .where(
                ToolDefinition.enabled.is_(True),
                (ToolDefinition.workspace_id.is_(None))
                | (ToolDefinition.workspace_id == workspace_id),
            )
            .order_by(ToolDefinition.name)
        )
    ).all()
    return list(rows)


async def resolve_tool_specs(
    session: AsyncSession, workspace_id: uuid.UUID, tool_ids: list[uuid.UUID]
) -> list[ToolSpec]:
    """Map persisted tool ids to executable registry specs.

    Rejects disabled tools, cross-workspace tools and ids with no server-side
    implementation. This is the only path from a stored id to executable code.
    """
    if not tool_ids:
        return []

    rows = (
        await session.scalars(select(ToolDefinition).where(ToolDefinition.id.in_(tool_ids)))
    ).all()
    found = {row.id: row for row in rows}
    missing = [str(tool_id) for tool_id in tool_ids if tool_id not in found]
    if missing:
        raise ResourceNotFound(
            "One or more selected tools no longer exist.",
            details={"tool_ids": missing},
        )

    specs: list[ToolSpec] = []
    for tool_id in tool_ids:
        row = found[tool_id]
        if not row.enabled:
            raise PolicyViolation("A selected tool is disabled.", details={"tool": row.name})
        if row.workspace_id is not None and row.workspace_id != workspace_id:
            raise ResourceNotFound("A selected tool is not available in this workspace.")
        tool = registry.get(row.name)
        if tool is None:
            raise PolicyViolation(
                "A selected tool has no server-side implementation.",
                details={"tool": row.name},
            )
        specs.append(tool.spec)
    return specs


def definition_to_dict(row: ToolDefinition) -> dict[str, Any]:
    """Serialise a tool definition for API responses."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "name": row.name,
        "version": row.version,
        "description": row.description,
        "input_schema": row.input_schema,
        "output_schema": row.output_schema,
        "risk_level": row.risk_level,
        "required_permissions": row.required_permissions,
        "requires_approval": row.requires_approval,
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "idempotent": row.idempotent,
        "enabled": row.enabled,
        "is_builtin": row.workspace_id is None,
    }


__all__ = [
    "definition_to_dict",
    "ensure_builtin_definitions",
    "list_tool_definitions",
    "resolve_tool_specs",
]
