"""Authentication and session management.

Sessions are server-side rows; the browser only holds an opaque token in an
HttpOnly cookie. Passwords are hashed with argon2id. No endpoint trusts a
user identity supplied by the client.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationRequired, ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    password_problems,
    verify_password,
)
from app.models.identity import AuthSession, User

logger = get_logger(__name__)

SESSION_REFRESH_WINDOW = timedelta(minutes=15)


def normalize_email(email: str) -> str:
    """Normalise an email address for storage and lookup."""
    return email.strip().lower()


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
) -> User:
    """Create a user account.

    Raises ``ValidationError`` for a weak password or duplicate email.
    """
    problems = password_problems(password)
    if problems:
        raise ValidationError(
            "The password does not meet the security policy.",
            details={"password_policy": problems},
        )

    normalized = normalize_email(email)
    existing = await session.scalar(select(User.id).where(User.email == normalized))
    if existing is not None:
        raise ConflictError("An account with this email address already exists.")

    user = User(
        email=normalized,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        status="active",
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:  # pragma: no cover - race condition guard
        await session.rollback()
        raise ConflictError("An account with this email address already exists.") from exc
    return user


async def authenticate_user(session: AsyncSession, *, email: str, password: str) -> User:
    """Verify credentials and return the user.

    Failures are deliberately indistinguishable between "unknown email" and
    "wrong password" to avoid account enumeration.
    """
    normalized = normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is None:
        # Spend comparable time on unknown accounts to blunt timing attacks.
        verify_password(password, hash_password("timing-equalizer"))
        raise AuthenticationRequired("Invalid email address or password.")
    if not verify_password(password, user.password_hash):
        raise AuthenticationRequired("Invalid email address or password.")
    if user.status != "active":
        raise AuthenticationRequired("This account is not active.")
    return user


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[AuthSession, str, str]:
    """Create a server-side session and return ``(row, session_token, csrf_token)``."""
    session_token = generate_token(32)
    csrf_token = generate_token(24)
    now = datetime.now(UTC)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_used_at=now,
        ip_address=(ip_address or None) and ip_address[:64],
        user_agent=(user_agent or None) and user_agent[:512],
    )
    session.add(auth_session)
    user.last_login_at = now
    await session.flush()
    return auth_session, session_token, csrf_token


async def load_session(
    session: AsyncSession, *, session_token: str
) -> tuple[AuthSession, User] | None:
    """Load and validate a session by its plaintext token."""
    if not session_token:
        return None
    now = datetime.now(UTC)
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(session_token))
    )
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    return row, user


async def revoke_session(session: AsyncSession, auth_session: AuthSession) -> None:
    """Revoke a session immediately."""
    if auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(UTC)
        session.add(auth_session)


async def revoke_all_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every active session for a user (used on password change)."""
    rows = (
        await session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
            )
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.revoked_at = now
    return len(rows)


async def purge_expired_sessions(session: AsyncSession) -> int:
    """Delete sessions that expired more than a day ago."""
    cutoff = datetime.now(UTC) - timedelta(days=1)
    rows = (
        await session.scalars(select(AuthSession).where(AuthSession.expires_at < cutoff))
    ).all()
    for row in rows:
        await session.delete(row)
    return len(rows)


__all__ = [
    "SESSION_REFRESH_WINDOW",
    "authenticate_user",
    "create_session",
    "load_session",
    "normalize_email",
    "purge_expired_sessions",
    "register_user",
    "revoke_all_user_sessions",
    "revoke_session",
]
