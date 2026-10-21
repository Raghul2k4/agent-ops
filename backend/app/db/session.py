"""Async engine, session factory and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _connect_args() -> dict[str, object]:
    """Driver options applied to every pooled connection.

    Deployed environments reach Postgres through the Supabase **transaction**
    pooler, where a server-side prepared statement cannot be reused by the next
    client that borrows the connection. psycopg keeps re-using a prepared
    statement unless the threshold is disabled, which surfaces as intermittent
    ``InvalidSqlStatementName`` errors - so statements are prepared per
    execution instead. The cost is negligible for this workload and it keeps
    development (direct connection) and production (pooler) behaviour identical.

    Timeouts are set per connection so a slow query or a forgotten transaction
    can never hold a pooled backend indefinitely.
    """
    return {
        "prepare_threshold": None,
        "application_name": "agentops-api",
        "options": (
            f"-c statement_timeout={settings.db_statement_timeout_ms} "
            f"-c idle_in_transaction_session_timeout={settings.db_idle_tx_timeout_ms}"
        ),
    }


def get_engine() -> AsyncEngine:
    """Return the lazily created async engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=_connect_args(),
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the lazily created async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine pool (called on application shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


__all__ = ["dispose_engine", "get_engine", "get_session", "get_session_factory"]
