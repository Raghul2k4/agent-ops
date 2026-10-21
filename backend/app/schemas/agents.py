"""Schemas for agents, versions and the playground/run entry point."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelParameters(BaseModel):
    """Provider-agnostic sampling parameters; unsupported values are rejected."""

    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=1024, ge=1, le=32000)
    timeout_seconds: int = Field(default=60, ge=5, le=300)


class ExecutionLimits(BaseModel):
    """Hard budgets enforced by the runtime, not by the model."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=8, ge=1, le=24)
    max_tool_calls: int = Field(default=8, ge=0, le=50)
    max_wall_clock_seconds: int = Field(default=120, ge=10, le=900)
    max_total_tokens: int = Field(default=20000, ge=100, le=200000)
    max_cost_usd: float = Field(default=1.0, ge=0.0, le=100.0)


class AgentConfiguration(BaseModel):
    """A complete, runnable agent configuration snapshot."""

    model_config = ConfigDict(extra="forbid")

    provider_id: uuid.UUID
    model_config_id: uuid.UUID
    # Snapshot of the model name so a historical version stays interpretable
    # even if the model config is later renamed or disabled.
    model_name: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1, max_length=32000)
    parameters: ModelParameters = Field(default_factory=ModelParameters)
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)
    tool_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    streaming: bool = False

    @field_validator("tool_ids")
    @classmethod
    def _unique_tools(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("tool_ids must not contain duplicates")
        return value


class AgentCreateRequest(BaseModel):
    """Create an agent from a template or from explicit settings."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    template_key: str | None = Field(default=None, max_length=64)
    provider_id: uuid.UUID
    model_config_id: uuid.UUID
    system_prompt: str | None = Field(default=None, min_length=1, max_length=32000)
    tool_names: list[str] | None = None
    parameters: ModelParameters | None = None
    limits: ExecutionLimits | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class AgentUpdateRequest(BaseModel):
    """Update agent metadata or replace the editable draft configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    draft_configuration: AgentConfiguration | None = None
    change_note: str | None = Field(default=None, max_length=500)


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str
    status: str
    draft_configuration: dict[str, Any]
    current_published_version_id: uuid.UUID | None = None
    current_version_number: int | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AgentVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    version_number: int
    configuration: dict[str, Any]
    configuration_hash: str
    change_summary: str
    created_by: uuid.UUID | None = None
    created_at: datetime


class AgentPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_summary: str = Field(default="", max_length=500)


class AgentRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: uuid.UUID


class AgentDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class AgentTemplateRead(BaseModel):
    key: str
    name: str
    description: str
    category: str
    system_prompt: str
    tool_names: list[str]
    parameters: ModelParameters


class AgentRunRequest(BaseModel):
    """Start a run against an immutable published version."""

    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any] = Field(default_factory=dict)
    version_id: uuid.UUID | None = None
    replay_of_run_id: uuid.UUID | None = None

    @field_validator("input")
    @classmethod
    def _require_message(cls, value: dict[str, Any]) -> dict[str, Any]:
        message = value.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("input.message must be a non-empty string")
        if len(message) > 16000:
            raise ValueError("input.message must be at most 16000 characters")
        return value


__all__ = [
    "AgentConfiguration",
    "AgentCreateRequest",
    "AgentDuplicateRequest",
    "AgentPublishRequest",
    "AgentRead",
    "AgentRollbackRequest",
    "AgentRunRequest",
    "AgentTemplateRead",
    "AgentUpdateRequest",
    "AgentVersionRead",
    "ExecutionLimits",
    "ModelParameters",
]
