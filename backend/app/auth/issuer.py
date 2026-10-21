"""Local development token issuance.

This module exists so AgentOps can run without a hosted Supabase project. It is
not an authentication provider for deployment: ``Settings`` refuses
``AUTH_MODE=local`` outside development/test, and ``issue_local_token`` checks
the environment again before signing anything.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import LOCAL_AUTH_ENVIRONMENTS, settings

LOCAL_AUDIENCE = "authenticated"
LOCAL_ALGORITHM = "HS256"


def local_auth_available() -> bool:
    """Whether this process may issue development tokens."""
    return settings.auth_mode == "local" and settings.environment in LOCAL_AUTH_ENVIRONMENTS


def issue_local_token(
    *, subject: uuid.UUID, email: str, ttl_minutes: int | None = None
) -> tuple[str, datetime]:
    """Return ``(access_token, expires_at)`` for a development identity."""
    if not local_auth_available():  # pragma: no cover - defence in depth
        raise RuntimeError("Local token issuance is disabled in this environment")

    now = datetime.now(UTC)
    expires_at = now + timedelta(
        minutes=ttl_minutes if ttl_minutes is not None else settings.local_jwt_ttl_minutes
    )
    payload = {
        "sub": str(subject),
        "email": email,
        "aud": LOCAL_AUDIENCE,
        "iss": settings.local_jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "role": "authenticated",
        "agentops": {"auth_mode": "local"},
    }
    token = jwt.encode(payload, settings.local_jwt_secret, algorithm=LOCAL_ALGORITHM)
    return token, expires_at


__all__ = ["LOCAL_ALGORITHM", "LOCAL_AUDIENCE", "issue_local_token", "local_auth_available"]
