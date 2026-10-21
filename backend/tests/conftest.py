"""Shared pytest fixtures.

The integration tier runs against a **real PostgreSQL database** (no SQLite
fallback: Postgres semantics are the target). Migrations are applied once per
session with Alembic, and tables are truncated between tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.deps import get_db
from app.core.config import settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

TRUNCATE_TABLES = (
    "workspace_preferences",
    "audit_events",
    "api_keys",
    "sessions",
    "workspace_members",
    "workspaces",
    "users",
)


def pytest_configure(config: pytest.Config) -> None:
    """Register the integration marker used across the suite."""
    config.addinivalue_line("markers", "integration: requires a PostgreSQL test database")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Return the URL of the dedicated test database."""
    url = os.getenv("TEST_DATABASE_URL") or settings.test_database_url
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not configured - integration tests need a PostgreSQL database"
        )
    return url


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> Iterator[None]:  # type: ignore[name-defined]
    """Apply all Alembic migrations to the test database once."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(config, "head")
    yield


@pytest_asyncio.fixture
async def engine(test_database_url: str, migrated_database: None) -> AsyncIterator:  # type: ignore[name-defined]
    """Async engine bound to the test database."""
    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[no-untyped-def]
    """Session factory for the test database."""
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:  # type: ignore[no-untyped-def]
    """A session bound to the test database, with clean tables."""
    from sqlalchemy import text

    async with session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE " + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session


class ApiClient(AsyncClient):
    """HTTP client that transparently attaches the CSRF header."""

    async def request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        method = kwargs.get("method") or (args[0] if args else "GET")
        if str(method).upper() in UNSAFE_METHODS:
            csrf = self.cookies.get("agentops_csrf")
            if csrf:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", csrf)
                kwargs["headers"] = headers
        return await super().request(*args, **kwargs)


@pytest_asyncio.fixture
async def app(session_factory) -> AsyncIterator:  # type: ignore[no-untyped-def]
    """The FastAPI application with the database dependency pointed at the test DB."""
    application = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[ApiClient]:  # type: ignore[no-untyped-def]
    """An HTTP client bound to the test application."""
    transport = ASGITransport(app=app)
    async with ApiClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Placeholder for future header-based fixtures."""
    return {}
