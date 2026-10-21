"""Provider and model configuration services.

Credentials are never persisted: ``secret_reference`` stores the *name* of a
server-side environment variable. Responses only ever expose that name and a
boolean, so a saved secret cannot be read back through the API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, ResourceNotFound, ValidationError
from app.models.providers import ModelConfig, ModelProvider
from app.providers.base import Provider, ProviderError
from app.providers.factory import DEFAULT_BASE_URLS, build_provider
from app.schemas.providers import (
    ModelConfigCreateRequest,
    ModelConfigUpdateRequest,
    ProviderCreateRequest,
    ProviderUpdateRequest,
    ProviderWithModels,
)

SIMULATION_DISPLAY_NAME = "Simulation (deterministic demo)"
SIMULATION_MODEL_NAME = "simulation-deterministic"

_ALLOWED_CONFIG_KEYS = {"timeout_seconds", "supports_tools", "supports_structured_output"}


def _validate_base_url(value: str, *, provider_type: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("base_url must use http or https.")
    if parsed.username or parsed.password:
        raise ValidationError("base_url must not contain credentials.")
    if not parsed.hostname:
        raise ValidationError("base_url must include a host.")
    # A local Ollama endpoint is expected to be plain HTTP. Cloud providers in
    # production must not send bearer tokens over cleartext.
    if (
        parsed.scheme == "http"
        and settings.environment == "production"
        and provider_type not in ("ollama", "simulation")
    ):
        raise ValidationError("base_url must use https for a hosted provider.")
    return value.rstrip("/")


def _validate_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(configuration) - _ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ValidationError(
            "Unsupported provider configuration keys.",
            details={"keys": unknown},
        )
    cleaned: dict[str, Any] = {}
    if "timeout_seconds" in configuration:
        try:
            timeout = int(configuration["timeout_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("configuration.timeout_seconds must be a number.") from exc
        if not 5 <= timeout <= 600:
            raise ValidationError("configuration.timeout_seconds must be between 5 and 600.")
        cleaned["timeout_seconds"] = timeout
    for key in ("supports_tools", "supports_structured_output"):
        if key in configuration:
            value = configuration[key]
            if not isinstance(value, bool):
                raise ValidationError(f"configuration.{key} must be a boolean.")
            cleaned[key] = value
    return cleaned


async def create_provider(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    payload: ProviderCreateRequest,
) -> ModelProvider:
    provider_type = payload.provider_type
    if provider_type == "simulation":
        base_url = None
    else:
        raw = payload.base_url or DEFAULT_BASE_URLS.get(provider_type)
        if not raw:
            raise ValidationError("base_url is required for this provider type.")
        base_url = _validate_base_url(raw, provider_type=provider_type)

    provider = ModelProvider(
        workspace_id=workspace_id,
        provider_type=provider_type,
        display_name=payload.display_name,
        base_url=base_url,
        secret_reference=payload.secret_reference,
        configuration=_validate_configuration(payload.configuration),
        status="connected" if provider_type == "simulation" else "unconfigured",
        last_health_check_at=datetime.now(UTC) if provider_type == "simulation" else None,
        created_by=actor_id,
    )
    session.add(provider)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("A provider with that name already exists.") from exc
    return provider


async def list_providers(session: AsyncSession, workspace_id: uuid.UUID) -> list[ModelProvider]:
    rows = (
        await session.scalars(
            select(ModelProvider)
            .where(ModelProvider.workspace_id == workspace_id)
            .order_by(ModelProvider.display_name)
        )
    ).all()
    return list(rows)


async def get_provider(
    session: AsyncSession, *, workspace_id: uuid.UUID, provider_id: uuid.UUID
) -> ModelProvider:
    provider = await session.scalar(
        select(ModelProvider).where(
            ModelProvider.workspace_id == workspace_id, ModelProvider.id == provider_id
        )
    )
    if provider is None:
        raise ResourceNotFound("Provider not found.")
    return provider


async def update_provider(
    session: AsyncSession,
    *,
    provider: ModelProvider,
    payload: ProviderUpdateRequest,
) -> ModelProvider:
    if payload.display_name is not None:
        provider.display_name = payload.display_name
    if payload.base_url is not None:
        if provider.provider_type == "simulation":
            raise ValidationError("The simulation provider does not use a base URL.")
        provider.base_url = _validate_base_url(
            payload.base_url, provider_type=provider.provider_type
        )
    if payload.secret_reference is not None:
        provider.secret_reference = payload.secret_reference or None
    if payload.configuration is not None:
        provider.configuration = _validate_configuration(payload.configuration)
    if payload.enabled is not None:
        provider.status = "unconfigured" if payload.enabled else "disabled"
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("A provider with that name already exists.") from exc
    return provider


async def delete_provider(session: AsyncSession, *, provider: ModelProvider) -> None:
    await session.delete(provider)
    await session.flush()


async def test_provider(
    session: AsyncSession, *, provider: ModelProvider
) -> tuple[bool, str | None, list[str], Provider | None]:
    checked_at = datetime.now(UTC)
    try:
        adapter = build_provider(provider)
    except ProviderError as exc:
        # Configuration is incomplete (for example the referenced environment
        # variable is unset). Record the diagnostic instead of failing the
        # request, so the UI can explain what the operator must fix.
        provider.last_health_check_at = checked_at
        provider.last_health_error = exc.message
        provider.status = "error"
        await session.flush()
        return False, exc.message, [], None

    ok, message = await adapter.health_check()
    models: list[str] = []
    if ok:
        try:
            models = await adapter.list_models()
        except ProviderError:
            # A reachable endpoint that cannot list models is still usable; the
            # operator can type a model name.
            models = []

    provider.last_health_check_at = checked_at
    provider.last_health_error = None if ok else (message or "The provider is unreachable.")
    provider.status = "connected" if ok else "error"
    await session.flush()
    return ok, message, models, adapter


async def ensure_simulation_provider(
    session: AsyncSession, *, workspace_id: uuid.UUID, actor_id: uuid.UUID | None
) -> ModelProvider:
    """Idempotently create the clearly labelled deterministic demo provider."""
    provider = await session.scalar(
        select(ModelProvider).where(
            ModelProvider.workspace_id == workspace_id,
            ModelProvider.provider_type == "simulation",
        )
    )
    if provider is not None:
        return provider

    provider = ModelProvider(
        workspace_id=workspace_id,
        provider_type="simulation",
        display_name=SIMULATION_DISPLAY_NAME,
        base_url=None,
        secret_reference=None,
        configuration={},
        status="connected",
        last_health_check_at=datetime.now(UTC),
        created_by=actor_id,
    )
    session.add(provider)
    await session.flush()

    has_default = await session.scalar(
        select(ModelConfig.id)
        .where(ModelConfig.workspace_id == workspace_id, ModelConfig.is_default.is_(True))
        .limit(1)
    )
    session.add(
        ModelConfig(
            workspace_id=workspace_id,
            provider_id=provider.id,
            model_name=SIMULATION_MODEL_NAME,
            display_name="Deterministic simulation",
            capabilities={
                "supports_tools": True,
                "supports_structured_output": False,
                "supports_streaming": False,
                "context_window": 8192,
            },
            pricing={},
            enabled=True,
            is_default=has_default is None,
        )
    )
    await session.flush()
    return provider


async def list_model_configs(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[tuple[ModelConfig, ModelProvider]]:
    rows = (
        await session.execute(
            select(ModelConfig, ModelProvider)
            .join(ModelProvider, ModelConfig.provider_id == ModelProvider.id)
            .where(ModelConfig.workspace_id == workspace_id)
            .order_by(ModelProvider.display_name, ModelConfig.model_name)
        )
    ).all()
    return [(model, provider) for model, provider in rows]


async def get_model_config(
    session: AsyncSession, *, workspace_id: uuid.UUID, model_id: uuid.UUID
) -> tuple[ModelConfig, ModelProvider]:
    row = (
        await session.execute(
            select(ModelConfig, ModelProvider)
            .join(ModelProvider, ModelConfig.provider_id == ModelProvider.id)
            .where(ModelConfig.workspace_id == workspace_id, ModelConfig.id == model_id)
        )
    ).first()
    if row is None:
        raise ResourceNotFound("Model not found.")
    return row[0], row[1]


async def _clear_default(session: AsyncSession, workspace_id: uuid.UUID) -> None:
    await session.execute(
        update(ModelConfig)
        .where(ModelConfig.workspace_id == workspace_id, ModelConfig.is_default.is_(True))
        .values(is_default=False)
    )


async def create_model_config(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider: ModelProvider,
    payload: ModelConfigCreateRequest,
) -> ModelConfig:
    if payload.is_default:
        await _clear_default(session, workspace_id)

    model = ModelConfig(
        workspace_id=workspace_id,
        provider_id=provider.id,
        model_name=payload.model_name,
        display_name=payload.display_name,
        capabilities=payload.capabilities.model_dump(mode="json"),
        default_parameters=payload.default_parameters,
        pricing=payload.pricing.model_dump(mode="json") if payload.pricing else {},
        enabled=payload.enabled,
        is_default=payload.is_default,
    )
    session.add(model)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("That model is already configured for this provider.") from exc
    return model


async def update_model_config(
    session: AsyncSession,
    *,
    model: ModelConfig,
    payload: ModelConfigUpdateRequest,
) -> ModelConfig:
    if payload.display_name is not None:
        model.display_name = payload.display_name
    if payload.capabilities is not None:
        model.capabilities = payload.capabilities.model_dump(mode="json")
    if payload.default_parameters is not None:
        model.default_parameters = payload.default_parameters
    if payload.pricing is not None:
        model.pricing = payload.pricing.model_dump(mode="json")
    if payload.enabled is not None:
        model.enabled = payload.enabled
        if not payload.enabled:
            model.is_default = False
    if payload.is_default is not None:
        if payload.is_default:
            await _clear_default(session, model.workspace_id)
        model.is_default = payload.is_default
    await session.flush()
    return model


async def delete_model_config(session: AsyncSession, *, model: ModelConfig) -> None:
    await session.delete(model)
    await session.flush()


def provider_read(provider: ModelProvider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "workspace_id": provider.workspace_id,
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "base_url": provider.base_url,
        "secret_reference": provider.secret_reference,
        "has_secret_reference": bool(provider.secret_reference),
        "configuration": provider.configuration,
        "status": provider.status,
        "last_health_check_at": provider.last_health_check_at,
        "last_health_error": provider.last_health_error,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def model_read(model: ModelConfig, provider: ModelProvider) -> dict[str, Any]:
    return {
        "id": model.id,
        "workspace_id": model.workspace_id,
        "provider_id": model.provider_id,
        "provider_type": provider.provider_type,
        "provider_display_name": provider.display_name,
        "model_name": model.model_name,
        "display_name": model.display_name,
        "capabilities": model.capabilities,
        "default_parameters": model.default_parameters,
        "pricing": model.pricing,
        "enabled": model.enabled,
        "is_default": model.is_default,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


async def provider_with_models(
    session: AsyncSession, provider: ModelProvider
) -> ProviderWithModels:
    rows = (
        await session.scalars(
            select(ModelConfig)
            .where(ModelConfig.provider_id == provider.id)
            .order_by(ModelConfig.model_name)
        )
    ).all()
    return ProviderWithModels(
        **provider_read(provider),
        models=[model_read(model, provider) for model in rows],
    )


__all__ = [
    "SIMULATION_DISPLAY_NAME",
    "SIMULATION_MODEL_NAME",
    "create_model_config",
    "create_provider",
    "delete_model_config",
    "delete_provider",
    "ensure_simulation_provider",
    "get_model_config",
    "get_provider",
    "list_model_configs",
    "list_providers",
    "model_read",
    "provider_read",
    "provider_with_models",
    "test_provider",
    "update_model_config",
    "update_provider",
]
