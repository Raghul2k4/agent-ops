"""Unit tests for the error taxonomy and envelope."""

from __future__ import annotations

import pytest

from app.core.errors import (
    AppError,
    AuthenticationRequired,
    ErrorCode,
    PermissionDenied,
    ResourceNotFound,
    ValidationError,
)


class TestErrorCodes:
    def test_expected_status_codes(self) -> None:
        assert ValidationError().status_code == 422
        assert AuthenticationRequired().status_code == 401
        assert PermissionDenied().status_code == 403
        assert ResourceNotFound().status_code == 404

    def test_retryable_flag_is_explicit(self) -> None:
        from app.core.errors import RateLimited

        assert RateLimited().retryable is True
        assert AuthenticationRequired().retryable is False

    def test_policy_violation_raises_alert(self) -> None:
        from app.core.errors import PolicyViolation

        assert PolicyViolation().alert is True


class TestErrorEnvelope:
    def test_payload_shape(self) -> None:
        error = AppError("boom", code=ErrorCode.INTERNAL_ERROR, details={"k": "v"})
        payload = error.to_payload("req-1")
        assert payload["error"]["code"] == "INTERNAL_ERROR"
        assert payload["error"]["message"] == "boom"
        assert payload["error"]["request_id"] == "req-1"
        assert payload["error"]["details"] == {"k": "v"}

    def test_details_are_omitted_when_empty(self) -> None:
        payload = AppError("boom").to_payload()
        assert "details" not in payload["error"]
        assert "request_id" not in payload["error"]


@pytest.mark.parametrize(
    "error_class",
    [ValidationError, AuthenticationRequired, PermissionDenied, ResourceNotFound],
)
def test_errors_are_app_errors(error_class: type[AppError]) -> None:
    with pytest.raises(AppError):
        raise error_class()
