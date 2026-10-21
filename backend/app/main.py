"""AgentOps FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.db.session import dispose_engine

logger = get_logger(__name__)

DESCRIPTION = """
AgentOps is an AI agent engineering and operations platform.

* **Build** agents and visual workflows
* **Execute** them against approved tools and model providers
* **Observe** every model call, tool call and decision in a persisted trace
* **Evaluate** quality with reproducible suites and regression gates
* **Govern** permissions, budgets and human approvals

All endpoints are versioned under `/api/v1` and require a Supabase access token
(or a scoped API key) presented as `Authorization: Bearer <token>`, unless the
endpoint is explicitly public.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: configure logging, dispose the pool on shutdown."""
    configure_logging(settings.log_level)
    logger.info(
        "app.started",
        app=settings.app_name,
        environment=settings.environment,
        version=__version__,
    )
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("app.stopped")


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="AgentOps API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "api": settings.api_prefix,
        }

    return app


app = create_app()

__all__ = ["app", "create_app"]
