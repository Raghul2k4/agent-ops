"""Identity, workspace and audit models.

These ORM classes map onto the tables created by the Supabase SQL migrations in
``supabase/migrations`` - the schema authority. The ORM never creates or alters
schema at runtime (``AGENTS.md`` sections 4A.4 and 24).

``app.profiles`` mirrors ``auth.users``: the primary key *is* the Supabase Auth
subject, so a deleted identity cascades to its profile. Password credentials do
not live here; ``app.local_credentials`` holds development-only hashes and is
never written when ``AUTH_MODE=supabase``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import Role
from app.db.base import Base, JSONPayload, TimestampMixin, UUIDPrimaryKeyMixin

PROFILE_STATUSES = ("active", "disabled", "pending")
MEMBER_STATUSES = ("active", "invited", "suspended")
AUDIT_OUTCOMES = ("success", "denied", "failure")


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Application profile for an identity owned by Supabase Auth."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(f"status IN {PROFILE_STATUSES}", name="profiles_status_valid"),
        # `uq_profiles_email_lower` (case-insensitive unique) and the
        # `auth.users(id)` foreign key are created by the SQL migration.
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    memberships: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        # `workspace_members` has two foreign keys to `profiles` (the member and
        # the inviter); the relationship must name the membership column.
        foreign_keys="WorkspaceMember.user_id",
    )


class LocalCredential(TimestampMixin, Base):
    """Development-only password credential.

    Only written when ``AUTH_MODE=local``. Supabase Auth owns credentials in
    every deployed environment, and the migration grants no policy at all on
    this table so the authenticated role can never reach it.
    """

    __tablename__ = "local_credentials"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant boundary. All domain data is scoped to a workspace."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )

    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(UUIDPrimaryKeyMixin, Base):
    """Membership of a profile in a workspace with a role and status."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_id_user_id"
        ),
        CheckConstraint(f"role IN {tuple(r.value for r in Role)}", name="member_role_valid"),
        CheckConstraint(f"status IN {MEMBER_STATUSES}", name="member_status_valid"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    profile: Mapped[Profile] = relationship(back_populates="memberships", foreign_keys=[user_id])


class ApiKey(UUIDPrimaryKeyMixin, Base):
    """Scoped API key for programmatic access.

    The plaintext key is shown once at creation; only its hash is persisted.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_workspace_id", "workspace_id"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="api_key_revoked_ok"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail of security-relevant actions."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_events_action", "action"),
        CheckConstraint(f"outcome IN {AUDIT_OUTCOMES}", name="audit_outcome_valid"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    sanitized_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspacePreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-user, per-workspace UI preferences (e.g. the last active workspace)."""

    __tablename__ = "workspace_preferences"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_preferences_workspace_id_user_id"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONPayload, nullable=False, default=dict, server_default="{}"
    )


__all__ = [
    "ApiKey",
    "AuditEvent",
    "LocalCredential",
    "Profile",
    "Workspace",
    "WorkspaceMember",
    "WorkspacePreference",
]
