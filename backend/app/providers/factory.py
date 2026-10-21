"""Build provider adapters from persisted provider rows."""

from __future__ import annotations

import os

import httpx

from app.core.config import settings
from app.models.providers import ModelProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.base import Provider, ProviderError, ProviderFailure
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.simulation import SimulationProvider

DEFAULT_BASE_URLS = {
    "ollama": "http://127.0.0.1:11434",
    "openai_compatible": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


def resolve_secret(provider: ModelProvider) -> str | None:
    """Read the credential from the server-side environment, never the row."""
    if not provider.secret_reference:
        return None
    value = os.environ.get(provider.secret_reference)
    return value or None


def build_provider(
    provider: ModelProvider,
    *,
    timeout_seconds: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Provider:
    """Instantiate the adapter for a provider row."""
    provider_type = provider.provider_type
    configuration = provider.configuration or {}
    timeout = float(
        timeout_seconds or configuration.get("timeout_seconds") or settings.ollama_timeout_seconds
    )

    if provider_type == "simulation":
        return SimulationProvider()

    base_url = provider.base_url or DEFAULT_BASE_URLS.get(provider_type)
    if not base_url:
        raise ProviderError(
            "This provider requires a base URL.",
            failure=ProviderFailure.UNAVAILABLE,
        )

    if provider_type == "ollama":
        return OllamaProvider(
            base_url,
            timeout_seconds=timeout,
            api_key=resolve_secret(provider),
            transport=transport,
        )

    secret = resolve_secret(provider)
    if provider_type == "openai_compatible":
        if provider.secret_reference and not secret:
            raise ProviderError(
                f"The server environment variable {provider.secret_reference} is not set.",
                failure=ProviderFailure.AUTHENTICATION,
            )
        return OpenAICompatibleProvider(
            base_url,
            api_key=secret,
            timeout_seconds=timeout,
            transport=transport,
            supports_tools=bool(configuration.get("supports_tools", True)),
            supports_structured_output=bool(configuration.get("supports_structured_output", True)),
        )

    if provider_type == "anthropic":
        if provider.secret_reference and not secret:
            raise ProviderError(
                f"The server environment variable {provider.secret_reference} is not set.",
                failure=ProviderFailure.AUTHENTICATION,
            )
        return AnthropicProvider(
            base_url,
            api_key=secret,
            timeout_seconds=timeout,
            transport=transport,
        )

    raise ProviderError(
        f"Unsupported provider type '{provider_type}'.",
        failure=ProviderFailure.UNAVAILABLE,
    )


__all__ = ["DEFAULT_BASE_URLS", "build_provider", "resolve_secret"]
