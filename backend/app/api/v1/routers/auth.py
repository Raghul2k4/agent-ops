"""Authentication endpoints: register, login, logout and CSRF rotation."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.errors import AuthenticationRequired
from app.core.logging import get_logger
from app.core.security import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    generate_token,
    hash_token,
)
from app.schemas.identity import (
    AuthResponse,
    CsrfTokenResponse,
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


def _set_session_cookies(
    response: Response, *, session_token: str, csrf_token: str, max_age_seconds: int
) -> None:
    common = {
        "max_age": max_age_seconds,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(SESSION_COOKIE_NAME, session_token, httponly=True, **common)
    # Readable by the SPA so it can echo the value in the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=False, **common)


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


async def _auth_payload(
    session: AsyncSession, user, response: Response
) -> AuthResponse:
    memberships = await workspace_service.list_workspaces_for_user(session, user=user)
    counts = await workspace_service.member_counts(session, [ws.id for ws, _ in memberships])
    from app.schemas.identity import WorkspaceRead

    return AuthResponse(
        user=UserRead.model_validate(user),
        workspaces=[
            WorkspaceRead(
                id=ws.id,
                name=ws.name,
                slug=ws.slug,
                owner_id=ws.owner_id,
                role=role,
                member_count=counts.get(ws.id),
                settings=ws.settings or {},
                created_at=ws.created_at,
                updated_at=ws.updated_at,
            )
            for ws, role in memberships
        ],
        expires_at=datetime.now(UTC),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register a new user and start a session."""
    user = await auth_service.register_user(
        session,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    auth_session, session_token, csrf_token = await auth_service.create_session(
        session,
        user=user,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await audit_service.record_event(
        session,
        action="auth.register",
        resource_type="user",
        resource_id=str(user.id),
        actor_id=user.id,
        outcome="success",
    )
    await session.commit()

    max_age = settings.session_ttl_hours * 3600
    _set_session_cookies(
        response, session_token=session_token, csrf_token=csrf_token, max_age_seconds=max_age
    )
    result = await _auth_payload(session, user, response)
    result.expires_at = auth_session.expires_at
    return result


@router.post("/login", response_model=AuthResponse, summary="Start a session")
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate and start a session."""
    user = await auth_service.authenticate_user(
        session, email=payload.email, password=payload.password
    )
    auth_session, session_token, csrf_token = await auth_service.create_session(
        session,
        user=user,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await audit_service.record_event(
        session,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        actor_id=user.id,
        outcome="success",
    )
    await session.commit()

    max_age = settings.session_ttl_hours * 3600
    _set_session_cookies(
        response, session_token=session_token, csrf_token=csrf_token, max_age_seconds=max_age
    )
    result = await _auth_payload(session, user, response)
    result.expires_at = auth_session.expires_at
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End the session")
async def logout(
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke the current session and clear the cookies."""
    if context.auth_session is not None:
        await auth_service.revoke_session(session, context.auth_session)
        await audit_service.record_event(
            session,
            action="auth.logout",
            resource_type="user",
            resource_id=str(context.user.id) if context.user else None,
            actor_id=context.actor_id,
            outcome="success",
        )
        await session.commit()
    _clear_session_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/csrf", response_model=CsrfTokenResponse, summary="Rotate the CSRF token")
async def rotate_csrf(
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> CsrfTokenResponse:
    """Issue a fresh CSRF token bound to the current session."""
    if context.auth_session is None:
        raise AuthenticationRequired("This endpoint requires an interactive session.")
    csrf_token = generate_token(24)
    context.auth_session.csrf_token_hash = hash_token(csrf_token)
    session.add(context.auth_session)
    await session.commit()
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        max_age=settings.session_ttl_hours * 3600,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return CsrfTokenResponse(csrf_token=csrf_token)


__all__ = ["router"]
