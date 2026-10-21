"""Tool contracts and the in-process tool registry.

A tool is defined in Python (never by a caller): its name, typed input model,
risk classification, required permissions and execution function all live in
the server-side registry. The database row in ``app.tool_definitions`` is a
mirror used by the UI and by run snapshots - it can never introduce executable
behaviour.

Models may *propose* a tool name and arguments, but both are untrusted input:
the executor resolves the tool from this registry and validates the arguments
against the registered Pydantic model before any code runs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission

RiskLevel = Literal["low", "medium", "high", "critical"]

TOOL_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


class ToolInput(BaseModel):
    """Base class for tool arguments: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


@dataclass(slots=True)
class ToolContext:
    """Everything a tool implementation may use."""

    session: AsyncSession
    workspace_id: uuid.UUID
    actor_id: uuid.UUID | None
    run_id: uuid.UUID | None
    permissions: frozenset[Permission] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Immutable description of a registered tool."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    risk_level: RiskLevel = "low"
    required_permissions: tuple[Permission, ...] = ()
    requires_approval: bool = False
    timeout_seconds: int = 30
    max_retries: int = 0
    idempotent: bool = True
    version: int = 1
    implementation_prefix: str = "crm"

    @property
    def implementation(self) -> str:
        return f"{self.implementation_prefix}.{self.name}"

    @property
    def definition_id(self) -> uuid.UUID:
        """Stable id so the DB mirror is idempotent across restarts."""
        return uuid.uuid5(TOOL_NAMESPACE, f"agentops:tool:{self.implementation}:{self.version}")

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


class Tool(Protocol):
    """A registered tool implementation."""

    spec: ToolSpec

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        """Run against already-validated arguments and return a typed result."""


class ToolApprovalRequiredError(Exception):
    """Raised instead of executing a tool that needs human approval.

    Carries the exact canonical argument hash so a future approval can be bound
    to this action (implemented in the approvals milestone).
    """

    def __init__(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        canonical_hash: str,
        risk_level: str,
        tool_definition_id: uuid.UUID,
    ) -> None:
        super().__init__(f"Tool '{tool_name}' requires approval.")
        self.tool_name = tool_name
        self.arguments = arguments
        self.canonical_hash = canonical_hash
        self.risk_level = risk_level
        self.tool_definition_id = tool_definition_id


class ToolRegistry:
    """Server-side registry of executable tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.spec.name in self._tools:
            raise ValueError(f"Tool '{tool.spec.name}' is already registered.")
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def by_name(self) -> dict[str, Tool]:
        return dict(self._tools)

    def specs(self) -> list[ToolSpec]:
        return sorted((tool.spec for tool in self._tools.values()), key=lambda spec: spec.name)


registry = ToolRegistry()


__all__ = [
    "RiskLevel",
    "Tool",
    "ToolApprovalRequiredError",
    "ToolContext",
    "ToolInput",
    "ToolRegistry",
    "ToolSpec",
    "registry",
]
