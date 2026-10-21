"""Authentication endpoints.

* ``GET  /auth/mode``     - how the browser should obtain a token (public)
* ``POST /auth/register`` - development-only account creation
* ``POST /auth/login``    - development-only password sign-in
* ``POST /auth/logout``   - records sign-out; the client discards its token

In a deployment Supabase Auth owns sign-up, sign-in, refresh and revocation;
the API only verifies the resulting access token. The development endpoints
return a clear ``PERMISSION_DENIED`` when ``AUTH_MODE=supabase`` so the browser
never silently falls back to a local credential path.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.api.v1.serializers import workspace_read
from app.auth.issuer import local_auth_available
from app.core.config import settings
from app.core.logging import get_logger
from app.models.identity import Profile
from app.schemas.identity import (
    AuthModeResponse,
    AuthResponse,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
)
from app.services import audit as audit_service
from app.services import auth as auth_service
from app.services import workspaces as workspace_service

logger = get_logger(__name__)

router = APIRouter(prefix=f"{settings.api_prefix}/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


async def _auth_response(
    session: AsyncSession,
    profile: Profile,
    *,
    access_token: str,
    expires_at: datetime,
) -> AuthResponse:
    memberships = await workspace_service.list_workspaces_for_user(session, profile=profile)
    counts = await workspace_service.member_counts(session, [ws.id for ws, _ in memberships])
    return AuthResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=UserRead.model_validate(profile),
        workspaces=[workspace_read(ws, role, counts.get(ws.id)) for ws, role in memberships],
    )


@router.get("/mode", response_model=AuthModeResponse, summary="Discover the auth mode")
async def auth_mode() -> AuthModeResponse:
    """Tell the browser whether to use Supabase Auth or the development issuer."""
    return AuthModeResponse(
        auth_mode=settings.auth_mode,
        local_sign_in_enabled=local_auth_available(),
        supabase_url=settings.supabase_url if settings.auth_mode == "supabase" else None,
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a development account",
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create an account and return an access token (development mode only)."""
    profile = await auth_service.register_local_user(
        session,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    access_token, expires_at = auth_service.issue_access_token(profile)
    await audit_service.record_event(
        session,
        action="auth.register",
        resource_type="profile",
        resource_id=str(profile.id),
        actor_id=profile.id,
        outcome="success",
        metadata={"auth_mode": "local", "client_ip": _client_ip(request)},
    )
    await session.commit()
    return await _auth_response(session, profile, access_token=access_token, expires_at=expires_at)


@router.post("/login", response_model=AuthResponse, summary="Development password sign-in")
async def login(
    payload: UserLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate with a development credential and return an access token."""
    profile = await auth_service.authenticate_local_user(
        session, email=payload.email, password=payload.password
    )
    access_token, expires_at = auth_service.issue_access_token(profile)
    await audit_service.record_event(
        session,
        action="auth.login",
        resource_type="profile",
        resource_id=str(profile.id),
        actor_id=profile.id,
        outcome="success",
        metadata={"auth_mode": "local", "client_ip": _client_ip(request)},
    )
    await session.commit()
    return await _auth_response(session, profile, access_token=access_token, expires_at=expires_at)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record sign-out",
    description=(
        "Appends an audit event for the sign-out. Access tokens are stateless and "
        "remain valid until they expire, so the client must also discard the token "
        "(and, in Supabase mode, call `supabase.auth.signOut()` to revoke the refresh token)."
    ),
)
async def logout(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Record the sign-out and return no content."""
    await audit_service.record_event(
        session,
        action="auth.logout",
        resource_type="profile",
        resource_id=str(context.profile.id) if context.profile else None,
        actor_id=context.actor_id,
        outcome="success",
        metadata={"auth_mode": settings.auth_mode},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
