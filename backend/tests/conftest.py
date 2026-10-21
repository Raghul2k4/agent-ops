"""Shared pytest fixtures.

The integration tier runs against a **real PostgreSQL database** (no SQLite
fallback: Postgres semantics are the target). The schema is created by applying
``supabase/migrations/*.sql`` with ``psql -f`` - the same files
``supabase db push`` applies - followed by the RLS policy regression checks, so
tests exercise the production schema rather than an ORM approximation.

Point ``TEST_DATABASE_URL`` at any disposable PostgreSQL database. Locally the
default targets the project cluster created by ``scripts/dev_db.ps1``
(port 55432). The connecting role must be able to create schemas, roles and
extensions: the migration shim creates the ``auth``/``app_private`` schemas and
the ``anon``/``authenticated``/``service_role`` roles when they are absent.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

# psycopg's async driver cannot run on the Windows ProactorEventLoop. pytest
# creates its event loops through the global policy, so set it before any test
# imports the application (which creates the async engine).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# The suite pins its own runtime posture so a developer `.env` aimed at a hosted
# project can never redirect tests at a real database or change the auth mode.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTH_MODE", "local")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.deps import get_db
from app.auth.verify import set_verifier
from app.core.config import settings
from app.db import session as db_session_module
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
RLS_CHECKS = REPO_ROOT / "supabase" / "tests" / "rls_policies.sql"

# `auth.users` is truncated too: profiles reference it, and in development the
# migration shim owns that table. On Supabase, tests never run against auth.
# Every app table is schema-qualified: the connecting role's search_path does
# not include `app`, and an unqualified name would silently target `public`.
TRUNCATE_TABLES = (
    "app.followup_drafts",
    "app.trace_spans",
    "app.run_events",
    "app.run_checkpoints",
    "app.approval_requests",
    "app.agent_runs",
    "app.agent_tools",
    "app.agent_versions",
    "app.agents",
    "app.crm_contacts",
    "app.crm_deals",
    "app.crm_customers",
    "app.crm_companies",
    "app.model_configs",
    "app.model_providers",
    "app.tool_definitions",
    "app.workspace_policies",
    "app.workspace_preferences",
    "app.audit_events",
    "app.api_keys",
    "app.workspace_members",
    "app.workspaces",
    "app.local_credentials",
    "app.profiles",
    "auth.users",
)


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers used across the suite."""
    config.addinivalue_line("markers", "integration: requires a PostgreSQL test database")
    config.addinivalue_line("markers", "security: security regression tests")


def _sync_dsn(url: str) -> str:
    """Convert a SQLAlchemy URL into the libpq DSN psql expects."""
    return url.replace("+psycopg", "").replace("+asyncpg", "")


@contextmanager
def _runtime_session_factory(factory: async_sessionmaker[AsyncSession]) -> Iterator[None]:
    """Temporarily point the runtime engine at the test session factory."""
    previous = db_session_module._session_factory
    db_session_module._session_factory = factory
    try:
        yield
    finally:
        db_session_module._session_factory = previous


def _find_psql() -> str:
    """Locate the psql binary (NEVER hardcode a version-specific path as the only option)."""
    override = os.getenv("PSQL_BIN")
    if override and Path(override).exists():
        return override

    found = shutil.which("psql")
    if found:
        return found

    for root in (Path("C:/Program Files/PostgreSQL"), Path("/usr/lib/postgresql")):
        if not root.exists():
            continue
        candidates = sorted(root.glob("*/bin/psql*"), reverse=True)
        if candidates:
            return str(candidates[0])

    pytest.skip("psql was not found; set PSQL_BIN to run database tests")


def _psql(psql: str, dsn: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # `psql` is resolved from a trusted local path (PSQL_BIN, PATH or the
    # PostgreSQL install directory), never from test data.
    result = subprocess.run([psql, dsn, *args], capture_output=True, text=True)  # noqa: S603
    if check and result.returncode != 0:
        raise RuntimeError(
            f"psql failed with exit code {result.returncode}:\n{result.stderr.strip()}"
        )
    return result


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Return the URL of the dedicated test database."""
    url = os.getenv("TEST_DATABASE_URL") or settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured - integration tests need PostgreSQL")
    return url


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> Iterator[None]:
    """Rebuild the schema from the Supabase migrations, once per session."""
    psql = _find_psql()
    dsn = _sync_dsn(test_database_url)

    probe = _psql(psql, dsn, "-tAc", "select 1", check=False)
    if probe.returncode != 0:
        pytest.skip(f"PostgreSQL test database is unreachable ({dsn}): {probe.stderr.strip()}")

    # Start from a clean slate so the migrations always run from zero.
    _psql(
        psql,
        dsn,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "drop schema if exists app cascade; "
        "drop schema if exists app_private cascade; "
        "drop schema if exists auth cascade;",
    )

    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:  # pragma: no cover - repository invariant
        raise RuntimeError(f"No migrations found in {MIGRATIONS_DIR}")

    for migration in migrations:
        _psql(psql, dsn, "-v", "ON_ERROR_STOP=1", "-f", str(migration))

    # RLS regression checks run as part of the schema build.
    _psql(psql, dsn, "-v", "ON_ERROR_STOP=1", "-f", str(RLS_CHECKS))
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
async def clean_database(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Empty every tenant table so each test starts from a known state."""
    async with session_factory() as session:
        await session.execute(
            text("TRUNCATE " + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")
        )
        await session.commit()


@pytest_asyncio.fixture
async def db_session(
    session_factory,  # type: ignore[no-untyped-def]
    clean_database: None,
) -> AsyncIterator[AsyncSession]:
    """A session bound to the (already truncated) test database."""
    async with session_factory() as session:
        yield session


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

    # Background runtime tasks open their own sessions through the module-level
    # factory, so point it at the test database for the duration of the test.
    with _runtime_session_factory(session_factory):
        yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app, clean_database: None) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """An HTTP client bound to the test application, with a clean database."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest_asyncio.fixture(autouse=True)
async def _reset_token_verifier() -> AsyncIterator[None]:
    """Never leak a verifier override between tests."""
    set_verifier(None)
    yield
    set_verifier(None)


@pytest.fixture
def register_user(client) -> Callable:  # type: ignore[no-untyped-def]
    """Register a development account and return the auth payload."""

    async def _register(payload: dict[str, str]) -> dict:
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _register


def auth_header(token: str) -> dict[str, str]:
    """Build the Authorization header for a bearer token.

    Kept here for reference; test modules define their own one-line helper so
    they never depend on importable test packages.
    """
    return {"Authorization": f"Bearer {token}"}
