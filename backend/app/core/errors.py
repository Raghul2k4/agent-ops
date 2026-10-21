"""Unified error taxonomy (`AGENTS.md` §27).

Every failure that reaches the API boundary is expressed as an `AppError` carrying:

* a stable machine-readable ``code``,
* a **safe** user-facing message (never a stack trace or internal detail),
* optional structured ``details``,
* whether the caller may retry, whether the failure is terminal, and whether it
  should raise an alert.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Canonical error codes."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_TOOL_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    EXECUTION_LIMIT_EXCEEDED = "EXECUTION_LIMIT_EXCEEDED"
    RUN_CANCELLED = "RUN_CANCELLED"
    WORKFLOW_VALIDATION_FAILED = "WORKFLOW_VALIDATION_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Extension beyond the spec's example list: uniqueness / state conflicts.
    CONFLICT = "CONFLICT"


class ErrorSpec:
    """Static behaviour of an error code."""

    __slots__ = ("status_code", "retryable", "terminal", "alert")

    def __init__(
        self,
        status_code: int,
        *,
        retryable: bool = False,
        terminal: bool = True,
        alert: bool = False,
    ) -> None:
        self.status_code = status_code
        self.retryable = retryable
        self.terminal = terminal
        self.alert = alert


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.VALIDATION_ERROR: ErrorSpec(422, retryable=False, terminal=True),
    ErrorCode.AUTHENTICATION_REQUIRED: ErrorSpec(401, retryable=False, terminal=True),
    ErrorCode.PERMISSION_DENIED: ErrorSpec(403, retryable=False, terminal=True),
    ErrorCode.RESOURCE_NOT_FOUND: ErrorSpec(404, retryable=False, terminal=True),
    ErrorCode.PROVIDER_UNAVAILABLE: ErrorSpec(503, retryable=True, terminal=False, alert=True),
    ErrorCode.PROVIDER_TIMEOUT: ErrorSpec(504, retryable=True, terminal=False),
    ErrorCode.RATE_LIMITED: ErrorSpec(429, retryable=True, terminal=False),
    ErrorCode.INVALID_TOOL_ARGUMENTS: ErrorSpec(422, retryable=False, terminal=True),
    ErrorCode.TOOL_EXECUTION_FAILED: ErrorSpec(500, retryable=False, terminal=True),
    ErrorCode.APPROVAL_REQUIRED: ErrorSpec(202, retryable=False, terminal=False),
    ErrorCode.APPROVAL_EXPIRED: ErrorSpec(409, retryable=False, terminal=True),
    ErrorCode.POLICY_VIOLATION: ErrorSpec(403, retryable=False, terminal=True, alert=True),
    ErrorCode.EXECUTION_LIMIT_EXCEEDED: ErrorSpec(429, retryable=False, terminal=True),
    ErrorCode.RUN_CANCELLED: ErrorSpec(409, retryable=False, terminal=True),
    ErrorCode.WORKFLOW_VALIDATION_FAILED: ErrorSpec(422, retryable=False, terminal=True),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, retryable=False, terminal=True, alert=True),
    ErrorCode.CONFLICT: ErrorSpec(409, retryable=False, terminal=True),
}


class AppError(Exception):
    """Base class for every expected application failure."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        retryable: bool | None = None,
        terminal: bool | None = None,
        alert: bool | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        spec = ERROR_SPECS[self.code]
        self.message = message or self.default_message
        self.details = details or {}
        self.status_code = status_code if status_code is not None else spec.status_code
        self.retryable = spec.retryable if retryable is None else retryable
        self.terminal = spec.terminal if terminal is None else terminal
        self.alert = spec.alert if alert is None else alert
        super().__init__(self.message)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        """Serialise into the API error envelope."""
        body: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            body["details"] = self.details
        if request_id:
            body["request_id"] = request_id
        return {"error": body}


class ValidationError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    default_message = "The request payload is invalid."


class AuthenticationRequired(AppError):
    code = ErrorCode.AUTHENTICATION_REQUIRED
    default_message = "Authentication is required to access this resource."


class PermissionDenied(AppError):
    code = ErrorCode.PERMISSION_DENIED
    default_message = "You do not have permission to perform this action."


class ResourceNotFound(AppError):
    code = ErrorCode.RESOURCE_NOT_FOUND
    default_message = "The requested resource does not exist."


class ConflictError(AppError):
    code = ErrorCode.CONFLICT
    default_message = "The request conflicts with the current state of the resource."


class PolicyViolation(AppError):
    code = ErrorCode.POLICY_VIOLATION
    default_message = "The action was blocked by a workspace policy."


class RateLimited(AppError):
    code = ErrorCode.RATE_LIMITED
    default_message = "Too many requests. Please retry later."


class InternalError(AppError):
    code = ErrorCode.INTERNAL_ERROR
    default_message = "An unexpected error occurred."


__all__ = [
    "AppError",
    "AuthenticationRequired",
    "ConflictError",
    "ERROR_SPECS",
    "ErrorCode",
    "ErrorSpec",
    "InternalError",
    "PermissionDenied",
    "PolicyViolation",
    "RateLimited",
    "ResourceNotFound",
    "ValidationError",
]
