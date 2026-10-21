"""Model provider and model configuration ORM mappings.

Secrets are never stored here: ``secret_reference`` names a server-side
environment variable that the provider adapter resolves at request time.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONPayload, TimestampMixin, UUIDPrimaryKeyMixin

PROVIDER_TYPES = ("ollama", "openai_compatible", "anthropic", "simulation")
PROVIDER_STATUSES = ("unconfigured", "connected", "error", "disabled")


class ModelProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configured model provider endpoint inside a workspace."""

    __tablename__ = "model_providers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "display_name", name="model_providers_name_unique"),
        CheckConstraint(f"provider_type IN {PROVIDER_TYPES}", name="model_providers_type_valid"),
        CheckConstraint(f"status IN {PROVIDER_STATUSES}", name="model_providers_status_valid"),
        Index("ix_model_providers_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Name of the environment variable holding the credential (never the value).
    secret_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unconfigured")
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )


class ModelConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A selectable model on a provider, with capability and pricing metadata."""

    __tablename__ = "model_configs"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="model_configs_model_unique"),
        Index("ix_model_configs_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    default_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    pricing: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = ["PROVIDER_STATUSES", "PROVIDER_TYPES", "ModelConfig", "ModelProvider"]
