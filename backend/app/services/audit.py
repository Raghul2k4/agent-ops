"""Audit trail recording (`AGENTS.md` §26).

Audit rows are append-only through normal application operations and never
contain secrets: metadata keys that look sensitive are dropped before writing.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import AuditEvent

_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "session_token",
)


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Drop obviously sensitive keys from audit metadata."""
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            continue
        if isinstance(value, str) and len(value) > 500:
            value = value[:500] + "...[truncated]"
        safe[key] = value
    return safe


async def record_event(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    workspace_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    outcome: str = "success",
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit event to the current transaction."""
    event = AuditEvent(
        workspace_id=workspace_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        sanitized_metadata=sanitize_metadata(metadata),
    )
    session.add(event)
    return event


__all__ = ["record_event", "sanitize_metadata"]
