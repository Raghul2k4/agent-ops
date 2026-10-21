"""Schemas for identity, workspaces and memberships."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.permissions import Role


class UserRegisterRequest(BaseModel):
    """Registration payload."""

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
    """Login payload."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserRead(BaseModel):
    """Public user representation."""

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
    """Result of a successful register/login."""

    user: UserRead
    workspaces: list[WorkspaceRead] = Field(default_factory=list)
    expires_at: datetime


class MeResponse(BaseModel):
    """Current identity and workspace memberships."""

    user: UserRead
    workspaces: list[WorkspaceRead] = Field(default_factory=list)


class CsrfTokenResponse(BaseModel):
    """CSRF token for state-changing requests."""

    csrf_token: str


__all__ = [
    "AuthResponse",
    "CsrfTokenResponse",
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
