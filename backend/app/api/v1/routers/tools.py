"""Tool registry endpoints (read-only in this milestone)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.access import workspace_role
from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.permissions import Permission
from app.schemas.tools import ToolDefinitionRead
from app.services import tools as tool_service

router = APIRouter(prefix=f"{settings.api_prefix}/tools", tags=["tools"])


@router.get("", response_model=list[ToolDefinitionRead], summary="List available tools")
async def list_tools(
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[ToolDefinitionRead]:
    """Return global built-in tools plus workspace-scoped definitions.

    Custom executable tools are not supported yet; definitions are declared in
    Python so a database row can never introduce code.
    """
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.TOOL_READ,
    )
    definitions = await tool_service.list_tool_definitions(session, workspace_id)
    await session.commit()
    return [
        ToolDefinitionRead(**tool_service.definition_to_dict(definition))
        for definition in definitions
    ]


__all__ = ["router"]
