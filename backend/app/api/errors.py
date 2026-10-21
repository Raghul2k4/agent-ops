"""Exception handlers producing the uniform error envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

_HTTP_STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.AUTHENTICATION_REQUIRED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.PROVIDER_UNAVAILABLE,
    504: ErrorCode.PROVIDER_TIMEOUT,
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that map every failure onto the AgentOps error envelope."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = _request_id(request)
        if exc.alert:
            logger.error(
                "app.error",
                code=exc.code.value,
                message=exc.message,
                path=request.url.path,
                request_id=request_id,
            )
        else:
            logger.info(
                "app.rejected",
                code=exc.code.value,
                message=exc.message,
                path=request.url.path,
                request_id=request_id,
            )
        payload = exc.to_payload(request_id)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = {
            "fields": [
                {
                    "location": ".".join(str(part) for part in error.get("loc", ())),
                    "message": error.get("msg", "invalid value"),
                    "type": error.get("type", "value_error"),
                }
                for error in exc.errors()
            ]
        }
        payload = AppError(
            "The request payload is invalid.",
            code=ErrorCode.VALIDATION_ERROR,
            details=details,
        ).to_payload(_request_id(request))
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        payload = AppError(
            str(exc.detail) if exc.detail else code.default_message
            if hasattr(code, "default_message")
            else "The request could not be completed.",
            code=code,
        ).to_payload(_request_id(request))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "app.unhandled_error",
            path=request.url.path,
            request_id=_request_id(request),
            error_type=type(exc).__name__,
        )
        payload = AppError(
            "An unexpected error occurred.",
            code=ErrorCode.INTERNAL_ERROR,
        ).to_payload(_request_id(request))
        return JSONResponse(status_code=500, content=payload)


__all__ = ["register_exception_handlers"]
