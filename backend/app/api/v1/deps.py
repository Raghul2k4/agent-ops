"""Request dependencies: authentication context, permission gates, pagination."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationRequired, PermissionDenied, ValidationError
from app.core.permissions import BASELINE_PERMISSIONS, Permission, Role, role_has_permission
from app.core.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    hash_token,
)
from app.db.session import get_session
from app.models.identity import ApiKey, AuthSession, User
from app.services import auth as auth_service

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(slots=True)
class AuthContext:
    """Resolved identity for the current request."""

    user: User | None = None
    auth_session: AuthSession | None = None
    api_key: ApiKey | None = None
    workspace_id: uuid.UUID | None = None
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    @property
    def actor_id(self) -> uuid.UUID | None:
        if self.user is not None:
            return self.user.id
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
    """Resolve the caller from a session cookie or a scoped API key."""
    api_key_context = await _authenticate_api_key(request, session)
    if api_key_context is not None:
        return api_key_context

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise AuthenticationRequired()

    loaded = await auth_service.load_session(session, session_token=token)
    if loaded is None:
        raise AuthenticationRequired("Your session has expired. Please sign in again.")
    auth_session, user = loaded

    if request.method.upper() in _UNSAFE_METHODS:
        _enforce_csrf(request, auth_session)

    auth_session.last_used_at = datetime.now(UTC)
    session.add(auth_session)

    return AuthContext(
        user=user,
        auth_session=auth_session,
        permissions=_permissions_for_user(session, user),
    )


async def _authenticate_api_key(request: Request, session: AsyncSession) -> AuthContext | None:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    presented = header[7:].strip()
    if not presented.startswith("agoa_"):
        return None

    api_key = await session.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_token(presented))
    )
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


def _enforce_csrf(request: Request, auth_session: AuthSession) -> None:
    """Double-submit CSRF validation for cookie-authenticated mutations."""
    header_value = request.headers.get(CSRF_HEADER_NAME)
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    if not header_value or not cookie_value:
        raise PermissionDenied("Missing CSRF token.")
    if header_value != cookie_value:
        raise PermissionDenied("Invalid CSRF token.")
    if hash_token(header_value) != auth_session.csrf_token_hash:
        raise PermissionDenied("Invalid CSRF token.")


async def _permissions_for_user(session: AsyncSession, user: User) -> frozenset[Permission]:
    """Union of permissions across every workspace the user belongs to."""
    from app.models.identity import WorkspaceMember  # local import avoids a cycle

    roles = (
        await session.scalars(
            select(WorkspaceMember.role).where(
                WorkspaceMember.user_id == user.id,
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


def require_permission(permission: Permission) -> Callable[..., AuthContext]:
    """Build a dependency that requires a permission."""

    async def dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not context.has(permission):
            raise PermissionDenied(
                f"This action requires the '{permission.value}' permission."
            )
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
