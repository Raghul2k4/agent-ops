"""Schemas for identity, authentication, workspaces and memberships."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import AuthMode
from app.core.permissions import Role


class UserRegisterRequest(BaseModel):
    """Development registration payload (``AUTH_MODE=local`` only)."""

    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name must not be blank")
        return cleaned


class UserLoginRequest(BaseModel):
    """Development login payload (``AUTH_MODE=local`` only)."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserRead(BaseModel):
    """Public profile representation (the identity is Supabase's ``auth.users`` id)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    status: str
    created_at: datetime


class WorkspaceCreateRequest(BaseModel):
    """Create a workspace."""

    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class WorkspaceUpdateRequest(BaseModel):
    """Update workspace metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    settings: dict[str, object] | None = None


class WorkspaceRead(BaseModel):
    """Workspace representation including the caller's role."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    role: Role | None = Field(default=None, description="Caller's role in this workspace")
    member_count: int | None = None
    settings: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MemberRead(BaseModel):
    """Workspace member representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    display_name: str
    role: Role
    status: str
    created_at: datetime


class MemberInviteRequest(BaseModel):
    """Add an existing user to a workspace."""

    email: EmailStr
    role: Role = Role.VIEWER


class MemberRoleUpdateRequest(BaseModel):
    """Change a member's role."""

    role: Role


class AuthResponse(BaseModel):
    """Result of a successful sign-in.

    ``access_token`` is a bearer token the client presents as
    ``Authorization: Bearer <token>``. In Supabase mode the client normally
    obtains it directly from Supabase Auth; this shape is also used by the
    development issuer so the SPA has a single session model.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_at: datetime
    user: UserRead
    workspaces: list[WorkspaceRead] = Field(default_factory=list)


class MeResponse(BaseModel):
    """Current identity and workspace memberships."""

    user: UserRead
    workspaces: list[WorkspaceRead] = Field(default_factory=list)


class AuthModeResponse(BaseModel):
    """How the browser should obtain an access token."""

    auth_mode: AuthMode
    local_sign_in_enabled: bool = Field(
        description="True only for the development issuer; never in a deployment."
    )
    supabase_url: str | None = None


__all__ = [
    "AuthModeResponse",
    "AuthResponse",
    "MeResponse",
    "MemberInviteRequest",
    "MemberRead",
    "MemberRoleUpdateRequest",
    "UserLoginRequest",
    "UserRead",
    "UserRegisterRequest",
    "WorkspaceCreateRequest",
    "WorkspaceRead",
    "WorkspaceUpdateRequest",
]
