"""Schemas for model providers, model configs and connection tests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderType = Literal["ollama", "openai_compatible", "anthropic", "simulation"]


class ModelCapabilities(BaseModel):
    """What a model can do.

    ``None`` means **unknown**, not supported. A capability is only asserted
    when it has been confirmed against the provider, so the platform never
    claims a model supports tool calling, structured output or streaming
    because it assumed so.
    """

    model_config = ConfigDict(extra="forbid")

    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_streaming: bool | None = None
    context_window: int | None = Field(default=None, ge=256, le=10_000_000)


class ModelPricing(BaseModel):
    """USD per million tokens. Unset values mean cost is unavailable, not zero."""

    model_config = ConfigDict(extra="forbid")

    input_per_million: float | None = Field(default=None, ge=0)
    output_per_million: float | None = Field(default=None, ge=0)


class ProviderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: ProviderType
    display_name: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=512)
    secret_reference: str | None = Field(
        default=None,
        max_length=80,
        pattern=r"^[A-Z][A-Z0-9_]{2,79}$",
        description="Name of a server-side environment variable holding the credential.",
    )
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name must not be blank")
        return cleaned


class ProviderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=512)
    secret_reference: str | None = Field(
        default=None, max_length=80, pattern=r"^[A-Z][A-Z0-9_]{2,79}$"
    )
    configuration: dict[str, Any] | None = None
    enabled: bool | None = None


class ModelConfigCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    pricing: ModelPricing | None = None
    enabled: bool = True
    is_default: bool = False


class ModelConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    capabilities: ModelCapabilities | None = None
    default_parameters: dict[str, Any] | None = None
    pricing: ModelPricing | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class ModelConfigRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    provider_id: uuid.UUID
    provider_type: str
    provider_display_name: str
    model_name: str
    display_name: str | None
    capabilities: dict[str, Any]
    default_parameters: dict[str, Any]
    pricing: dict[str, Any]
    enabled: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProviderRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    provider_type: str
    display_name: str
    base_url: str | None
    secret_reference: str | None = Field(
        description="Environment variable name only - never the credential value."
    )
    has_secret_reference: bool = Field(description="Whether a credential reference is configured.")
    configuration: dict[str, Any]
    status: str
    last_health_check_at: datetime | None
    last_health_error: str | None
    created_at: datetime
    updated_at: datetime


class ProviderWithModels(ProviderRead):
    models: list[ModelConfigRead] = Field(default_factory=list)


class ProviderTestResult(BaseModel):
    ok: bool
    status: str
    message: str | None = None
    models: list[str] = Field(default_factory=list)
    checked_at: datetime


__all__ = [
    "ModelCapabilities",
    "ModelConfigCreateRequest",
    "ModelConfigRead",
    "ModelConfigUpdateRequest",
    "ModelPricing",
    "ProviderCreateRequest",
    "ProviderRead",
    "ProviderTestResult",
    "ProviderType",
    "ProviderUpdateRequest",
    "ProviderWithModels",
]
