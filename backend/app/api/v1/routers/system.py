"""System endpoints: liveness, readiness and current identity."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.errors import PermissionDenied
from app.core.logging import get_logger
from app.schemas.common import HealthStatus, ReadinessStatus
from app.schemas.identity import MeResponse, UserRead
from app.services import workspaces as workspace_service

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
async def health() -> HealthStatus:
    """Process liveness. Does not touch the database."""
    from app import __version__

    return HealthStatus(
        status="ok",
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessStatus, summary="Readiness probe")
async def ready(session: AsyncSession = Depends(get_db)) -> ReadinessStatus:
    """Readiness: verifies that required dependencies can be reached."""
    checks: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised only on a broken database
        logger.warning("readiness.database_failed", error=str(exc))
        checks["database"] = "unavailable"

    status = "ready" if all(value == "ok" for value in checks.values()) else "degraded"
    return ReadinessStatus(status=status, checks=checks)


@router.get(f"{settings.api_prefix}/me", response_model=MeResponse, summary="Current identity")
async def me(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return the authenticated user and the workspaces they belong to."""
    user = context.user
    if user is None:
        raise PermissionDenied(
            "This endpoint requires an interactive session; API keys are not supported here."
        )

    memberships = await workspace_service.list_workspaces_for_user(session, user=user)
    counts = await workspace_service.member_counts(session, [ws.id for ws, _ in memberships])
    return MeResponse(
        user=UserRead.model_validate(user),
        workspaces=[
            _workspace_read(ws, role, counts.get(ws.id))
            for ws, role in memberships
        ],
    )


def _workspace_read(workspace, role, member_count):  # type: ignore[no-untyped-def]
    from app.schemas.identity import WorkspaceRead

    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        role=role,
        member_count=member_count,
        settings=workspace.settings or {},
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


__all__ = ["router"]
