"""Request dependencies: authentication context, permission gates, pagination.

Every protected request presents ``Authorization: Bearer <token>``. The token is
either an AgentOps API key (``agoa_...``) or an access token verified
cryptographically against the configured issuer (``app/auth``). There is no
cookie or CSRF path: a bearer header cannot be attached by a cross-site form
post, which removes that entire class of attack.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.claims import TokenClaims, TokenError
from app.auth.verify import get_verifier
from app.core.errors import AuthenticationRequired, PermissionDenied, ValidationError
from app.core.logging import get_logger
from app.core.permissions import BASELINE_PERMISSIONS, Permission, Role, role_has_permission
from app.core.security import hash_token, is_api_key
from app.db.session import get_session
from app.models.identity import ApiKey, Profile
from app.services import auth as auth_service

logger = get_logger(__name__)


@dataclass(slots=True)
class AuthContext:
    """Resolved identity for the current request."""

    profile: Profile | None = None
    claims: TokenClaims | None = None
    api_key: ApiKey | None = None
    workspace_id: uuid.UUID | None = None
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    @property
    def actor_id(self) -> uuid.UUID | None:
        if self.profile is not None:
            return self.profile.id
        return self.api_key.created_by if self.api_key else None

    @property
    def is_api_key(self) -> bool:
        return self.api_key is not None

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions


async def get_db() -> AsyncIterator[AsyncSession]:
    """Database session dependency."""
    async for session in get_session():
        yield session


async def get_auth_context(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Resolve the caller from a bearer access token or a scoped API key."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise AuthenticationRequired("Provide an access token as 'Authorization: Bearer <token>'.")

    presented = authorization[7:].strip()
    if not presented:
        raise AuthenticationRequired()

    if is_api_key(presented):
        return await _authenticate_api_key(presented, session)

    try:
        claims = await get_verifier().verify(presented)
    except TokenError as exc:
        # The reason is logged for operators but never returned to the caller:
        # token contents and failure modes must not be probeable.
        logger.info("auth.token_rejected", reason=str(exc))
        raise AuthenticationRequired("Your access token is invalid or has expired.") from exc

    profile = await auth_service.resolve_profile(session, claims)
    return AuthContext(
        profile=profile,
        claims=claims,
        permissions=await _permissions_for_profile(session, profile),
    )


async def _authenticate_api_key(presented: str, session: AsyncSession) -> AuthContext:
    api_key = await session.scalar(select(ApiKey).where(ApiKey.key_hash == hash_token(presented)))
    if api_key is None or api_key.revoked_at is not None:
        raise AuthenticationRequired("Invalid API key.")
    if api_key.expires_at is not None and api_key.expires_at <= datetime.now(UTC):
        raise AuthenticationRequired("This API key has expired.")

    scopes: set[Permission] = set()
    for raw in api_key.scopes or []:
        try:
            scopes.add(Permission(raw))
        except ValueError:
            continue

    api_key.last_used_at = datetime.now(UTC)
    session.add(api_key)

    return AuthContext(
        api_key=api_key,
        workspace_id=api_key.workspace_id,
        permissions=frozenset(scopes),
    )


async def _permissions_for_profile(
    session: AsyncSession, profile: Profile
) -> frozenset[Permission]:
    """Union of permissions across every workspace the profile belongs to."""
    from app.models.identity import WorkspaceMember  # local import avoids a cycle

    roles = (
        await session.scalars(
            select(WorkspaceMember.role).where(
                WorkspaceMember.user_id == profile.id,
                WorkspaceMember.status == "active",
            )
        )
    ).all()
    permissions: set[Permission] = set(BASELINE_PERMISSIONS)
    for role in roles:
        try:
            parsed = Role(role)
        except ValueError:  # pragma: no cover - defensive
            continue
        permissions.update(
            permission for permission in Permission if role_has_permission(parsed, permission)
        )
    return frozenset(permissions)


def require_permission(permission: Permission) -> Callable[..., Awaitable[AuthContext]]:
    """Build a dependency that requires a permission."""

    async def dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not context.has(permission):
            raise PermissionDenied(f"This action requires the '{permission.value}' permission.")
        return context

    return dependency


def require_workspace_scope(context: AuthContext, workspace_id: uuid.UUID) -> None:
    """Ensure an API-key caller may only act inside its own workspace."""
    if context.is_api_key and context.workspace_id != workspace_id:
        raise PermissionDenied("This API key is not valid for that workspace.")


def parse_cursor(cursor: str | None) -> uuid.UUID | None:
    """Parse an opaque list cursor (currently a UUID)."""
    if not cursor:
        return None
    try:
        return uuid.UUID(cursor)
    except ValueError as exc:
        raise ValidationError("The pagination cursor is invalid.") from exc


__all__ = [
    "AuthContext",
    "get_auth_context",
    "get_db",
    "parse_cursor",
    "require_permission",
    "require_workspace_scope",
]
