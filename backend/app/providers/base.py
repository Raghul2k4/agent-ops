"""Provider-neutral model contracts.

Every adapter translates its wire format into these types, so the runtime never
sees vendor-specific payloads. Capability metadata is explicit: a provider that
cannot call tools says so instead of silently ignoring the tool list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ProviderFailure(StrEnum):
    """Normalised provider failure categories."""

    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "PROVIDER_TIMEOUT"
    AUTHENTICATION = "PROVIDER_AUTHENTICATION"
    RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"


class ProviderError(Exception):
    """A provider call failed in a categorised, safely reportable way."""

    def __init__(
        self,
        message: str,
        *,
        failure: ProviderFailure = ProviderFailure.UNAVAILABLE,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.failure = failure
        self.retryable = retryable
        self.status_code = status_code


class ToolSpec(BaseModel):
    """A tool contract offered to the model."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ModelToolCall(BaseModel):
    """A tool call proposed by a model. Arguments are untrusted input."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """A provider-neutral chat message.

    ``tool_calls`` is populated on assistant turns so a multi-step tool loop can
    be replayed to the provider exactly as it happened.
    """

    model_config = ConfigDict(extra="forbid")

    role: str  # system | user | assistant | tool
    content: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: list[ModelToolCall] = Field(default_factory=list)


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[ChatMessage]
    tools: list[ToolSpec] = Field(default_factory=list)
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    timeout_seconds: float = 60.0
    structured_output: dict[str, Any] | None = None


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: ModelUsage = Field(default_factory=ModelUsage)
    model: str = ""


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_streaming: bool = False
    context_window: int | None = None


@dataclass(slots=True)
class ProviderContext:
    """Everything an adapter needs to reach its endpoint."""

    provider_type: str
    base_url: str
    api_key: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0


@runtime_checkable
class Provider(Protocol):
    """Adapter contract implemented by every provider integration."""

    provider_type: str

    def capabilities(self, model: str) -> ProviderCapabilities:
        """Capabilities for a model; adapters may return conservative defaults."""

    async def health_check(self) -> tuple[bool, str | None]:
        """Return (reachable, sanitized error). Never raises for a normal outage."""

    async def chat(self, request: ModelRequest) -> ModelResponse:
        """Execute one model turn. Raises ``ProviderError`` on failure."""

    async def list_models(self) -> list[str]:
        """Best-effort model listing; return an empty list when unsupported."""


__all__ = [
    "ChatMessage",
    "ModelRequest",
    "ModelResponse",
    "ModelToolCall",
    "ModelUsage",
    "Provider",
    "ProviderCapabilities",
    "ProviderContext",
    "ProviderError",
    "ProviderFailure",
    "ToolSpec",
]
