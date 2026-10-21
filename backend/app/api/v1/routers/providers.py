"""Model provider and model configuration endpoints.

Responses never contain credential values, only the environment-variable name
(``secret_reference``) and whether it is configured.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.access import workspace_role
from app.api.v1.deps import AuthContext, get_auth_context, get_db
from app.core.config import settings
from app.core.permissions import Permission
from app.schemas.providers import (
    ModelConfigCreateRequest,
    ModelConfigRead,
    ModelConfigUpdateRequest,
    ProviderCreateRequest,
    ProviderTestResult,
    ProviderUpdateRequest,
    ProviderWithModels,
)
from app.services import audit as audit_service
from app.services import providers as provider_service

router = APIRouter(prefix=f"{settings.api_prefix}/models", tags=["models"])


@router.get("/providers", response_model=list[ProviderWithModels], summary="List providers")
async def list_providers(
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[ProviderWithModels]:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_READ,
    )
    providers = await provider_service.list_providers(session, workspace_id)
    return [
        await provider_service.provider_with_models(session, provider) for provider in providers
    ]


@router.post(
    "/providers",
    response_model=ProviderWithModels,
    status_code=status.HTTP_201_CREATED,
    summary="Create a provider",
)
async def create_provider(
    payload: ProviderCreateRequest,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ProviderWithModels:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    provider = await provider_service.create_provider(
        session,
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        payload=payload,
    )
    await audit_service.record_event(
        session,
        action="provider.create",
        resource_type="model_provider",
        resource_id=str(provider.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={
            "provider_type": provider.provider_type,
            "display_name": provider.display_name,
            "secret_reference": provider.secret_reference,
        },
    )
    await session.commit()
    return await provider_service.provider_with_models(session, provider)


@router.post(
    "/providers/simulation",
    response_model=ProviderWithModels,
    summary="Ensure the labelled deterministic simulation provider exists",
)
async def ensure_simulation_provider(
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ProviderWithModels:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    provider = await provider_service.ensure_simulation_provider(
        session, workspace_id=workspace_id, actor_id=context.actor_id
    )
    await audit_service.record_event(
        session,
        action="provider.ensure_simulation",
        resource_type="model_provider",
        resource_id=str(provider.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={"provider_type": "simulation"},
    )
    await session.commit()
    return await provider_service.provider_with_models(session, provider)


@router.get(
    "/providers/{provider_id}",
    response_model=ProviderWithModels,
    summary="Get a provider",
)
async def get_provider(
    provider_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ProviderWithModels:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_READ,
    )
    provider = await provider_service.get_provider(
        session, workspace_id=workspace_id, provider_id=provider_id
    )
    return await provider_service.provider_with_models(session, provider)


@router.patch(
    "/providers/{provider_id}",
    response_model=ProviderWithModels,
    summary="Update a provider",
)
async def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdateRequest,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ProviderWithModels:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    provider = await provider_service.get_provider(
        session, workspace_id=workspace_id, provider_id=provider_id
    )
    await provider_service.update_provider(session, provider=provider, payload=payload)
    await audit_service.record_event(
        session,
        action="provider.update",
        resource_type="model_provider",
        resource_id=str(provider.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={"display_name": provider.display_name, "status": provider.status},
    )
    await session.commit()
    return await provider_service.provider_with_models(session, provider)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a provider",
)
async def delete_provider(
    provider_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    provider = await provider_service.get_provider(
        session, workspace_id=workspace_id, provider_id=provider_id
    )
    name = provider.display_name
    await provider_service.delete_provider(session, provider=provider)
    await audit_service.record_event(
        session,
        action="provider.delete",
        resource_type="model_provider",
        resource_id=str(provider_id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={"display_name": name},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/providers/{provider_id}/test",
    response_model=ProviderTestResult,
    summary="Test a provider connection",
)
async def test_provider(
    provider_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ProviderTestResult:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    provider = await provider_service.get_provider(
        session, workspace_id=workspace_id, provider_id=provider_id
    )
    ok, message, models, _adapter = await provider_service.test_provider(session, provider=provider)
    await audit_service.record_event(
        session,
        action="provider.test",
        resource_type="model_provider",
        resource_id=str(provider.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        outcome="success" if ok else "failure",
        metadata={"status": provider.status},
    )
    await session.commit()
    return ProviderTestResult(
        ok=ok,
        status=provider.status,
        message=message,
        models=models,
        checked_at=provider.last_health_check_at or provider.updated_at,
    )


@router.post(
    "/providers/{provider_id}/models",
    response_model=ModelConfigRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a model on a provider",
)
async def create_model_config(
    provider_id: uuid.UUID,
    payload: ModelConfigCreateRequest,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ModelConfigRead:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    provider = await provider_service.get_provider(
        session, workspace_id=workspace_id, provider_id=provider_id
    )
    model = await provider_service.create_model_config(
        session, workspace_id=workspace_id, provider=provider, payload=payload
    )
    await audit_service.record_event(
        session,
        action="model.create",
        resource_type="model_config",
        resource_id=str(model.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={"provider_id": str(provider.id), "model_name": model.model_name},
    )
    await session.commit()
    return ModelConfigRead(**provider_service.model_read(model, provider))


@router.get("", response_model=list[ModelConfigRead], summary="List configured models")
async def list_model_configs(
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[ModelConfigRead]:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_READ,
    )
    rows = await provider_service.list_model_configs(session, workspace_id)
    return [
        ModelConfigRead(**provider_service.model_read(model, provider)) for model, provider in rows
    ]


@router.patch("/{model_id}", response_model=ModelConfigRead, summary="Update a model configuration")
async def update_model_config(
    model_id: uuid.UUID,
    payload: ModelConfigUpdateRequest,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> ModelConfigRead:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    model, provider = await provider_service.get_model_config(
        session, workspace_id=workspace_id, model_id=model_id
    )
    await provider_service.update_model_config(session, model=model, payload=payload)
    await audit_service.record_event(
        session,
        action="model.update",
        resource_type="model_config",
        resource_id=str(model.id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={"model_name": model.model_name, "enabled": model.enabled},
    )
    await session.commit()
    # `updated_at` is maintained by the database, so the ORM attribute is
    # expired after the commit and must be reloaded before serialization.
    await session.refresh(model)
    return ModelConfigRead(**provider_service.model_read(model, provider))


@router.delete(
    "/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a model configuration",
)
async def delete_model_config(
    model_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await workspace_role(
        session,
        context=context,
        workspace_id=workspace_id,
        permission=Permission.PROVIDER_WRITE,
    )
    model, _provider = await provider_service.get_model_config(
        session, workspace_id=workspace_id, model_id=model_id
    )
    name = model.model_name
    await provider_service.delete_model_config(session, model=model)
    await audit_service.record_event(
        session,
        action="model.delete",
        resource_type="model_config",
        resource_id=str(model_id),
        workspace_id=workspace_id,
        actor_id=context.actor_id,
        metadata={"model_name": name},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
