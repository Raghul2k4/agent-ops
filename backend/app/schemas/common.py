"""Shared schema primitives: error envelope, pagination and health payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ErrorBody(BaseModel):
    """Machine-readable error payload."""

    code: str = Field(description="Stable error code, e.g. PERMISSION_DENIED")
    message: str = Field(description="Safe, user-facing message")
    retryable: bool = Field(default=False, description="Whether the caller may retry")
    details: dict[str, object] | None = Field(default=None)
    request_id: str | None = Field(default=None)


class ErrorResponse(BaseModel):
    """Uniform error envelope returned by every failing endpoint."""

    error: ErrorBody


class Page[T](BaseModel):
    """Cursor-paginated collection."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[T]
    next_cursor: str | None = Field(default=None, description="Opaque cursor for the next page")
    total: int | None = Field(default=None, description="Total items, when cheap to compute")
    has_more: bool = Field(default=False)


class HealthStatus(BaseModel):
    """Liveness payload."""

    status: str
    app: str
    version: str
    environment: str


class ReadinessStatus(BaseModel):
    """Readiness payload including dependency checks."""

    status: str
    checks: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "ErrorBody",
    "ErrorResponse",
    "HealthStatus",
    "Page",
    "ReadinessStatus",
]
