"""Schemas for the server-side tool registry mirror."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class ToolDefinitionRead(BaseModel):
    """A registered tool contract as exposed to the UI.

    The row is descriptive: executable behaviour lives only in the server-side
    registry.
    """

    id: uuid.UUID
    workspace_id: uuid.UUID | None = None
    name: str
    version: int
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: str
    required_permissions: list[str]
    requires_approval: bool
    timeout_seconds: int
    max_retries: int
    idempotent: bool
    enabled: bool
    is_builtin: bool


__all__ = ["ToolDefinitionRead"]
