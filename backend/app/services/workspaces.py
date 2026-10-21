"""Workspace and membership services.

All reads and writes are tenant-scoped: a non-member receives
``RESOURCE_NOT_FOUND`` rather than ``PERMISSION_DENIED`` so that workspace
existence is not leaked across tenants.
"""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ResourceNotFound, ValidationError
from app.core.permissions import Role
from app.models.identity import Profile, Workspace, WorkspaceMember

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a workspace name into a URL-safe slug."""
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug[:60] or "workspace"


async def _unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    candidate = base
    for _ in range(10):
        exists = await session.scalar(select(Workspace.id).where(Workspace.slug == candidate))
        if exists is None:
            return candidate
        candidate = f"{base}-{secrets.token_hex(3)}"
    raise ConflictError("Could not allocate a unique workspace identifier.")


async def create_workspace(
    session: AsyncSession, *, owner: Profile, name: str
) -> tuple[Workspace, WorkspaceMember]:
    """Create a workspace and register the creator as owner."""
    slug = await _unique_slug(session, name)
    workspace = Workspace(name=name.strip(), slug=slug, owner_id=owner.id, settings={})
    session.add(workspace)
    await session.flush()

    membership = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=owner.id,
        role=Role.OWNER.value,
        status="active",
    )
    session.add(membership)
    await session.flush()
    return workspace, membership


async def list_workspaces_for_user(
    session: AsyncSession, *, profile: Profile
) -> list[tuple[Workspace, Role]]:
    """Return every workspace the profile is an active member of."""
    rows = (
        await session.execute(
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                WorkspaceMember.user_id == profile.id,
                WorkspaceMember.status == "active",
            )
            .order_by(Workspace.created_at.asc())
        )
    ).all()
    return [(workspace, Role(member.role)) for workspace, member in rows]


async def get_workspace_for_member(
    session: AsyncSession, *, workspace_id: uuid.UUID, profile: Profile
) -> tuple[Workspace, Role]:
    """Load a workspace the profile is a member of, or raise ``RESOURCE_NOT_FOUND``."""
    row = (
        await session.execute(
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMember.user_id == profile.id,
                WorkspaceMember.status == "active",
            )
        )
    ).first()
    if row is None:
        raise ResourceNotFound("Workspace not found.")
    workspace, membership = row
    return workspace, Role(membership.role)


async def member_counts(
    session: AsyncSession, workspace_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Return active member counts keyed by workspace id."""
    if not workspace_ids:
        return {}
    rows = (
        await session.execute(
            select(WorkspaceMember.workspace_id, func.count())
            .where(
                WorkspaceMember.workspace_id.in_(workspace_ids),
                WorkspaceMember.status == "active",
            )
            .group_by(WorkspaceMember.workspace_id)
        )
    ).all()
    return dict(rows)


async def list_members(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[tuple[WorkspaceMember, Profile]]:
    """List workspace members with their profile records."""
    rows = (
        await session.execute(
            select(WorkspaceMember, Profile)
            .join(Profile, Profile.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at.asc())
        )
    ).all()
    return [(member, profile) for member, profile in rows]


async def add_member(
    session: AsyncSession,
    *,
    workspace: Workspace,
    email: str,
    role: Role,
    invited_by: uuid.UUID | None = None,
) -> WorkspaceMember:
    """Add an existing platform user to a workspace."""
    normalized = email.strip().lower()
    profile = await session.scalar(select(Profile).where(func.lower(Profile.email) == normalized))
    if profile is None:
        raise ResourceNotFound("No user exists with that email address.")

    existing = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == profile.id,
        )
    )
    if existing is not None:
        raise ConflictError("That user is already a member of this workspace.")

    membership = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=profile.id,
        role=role.value,
        status="active",
        invited_by=invited_by,
    )
    session.add(membership)
    try:
        await session.flush()
    except IntegrityError as exc:  # pragma: no cover - race condition guard
        await session.rollback()
        raise ConflictError("That user is already a member of this workspace.") from exc
    return membership


async def change_member_role(
    session: AsyncSession, *, member: WorkspaceMember, role: Role
) -> WorkspaceMember:
    """Change a member's role, protecting the last owner."""
    if member.role == Role.OWNER.value and role != Role.OWNER:
        owners = await session.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == member.workspace_id,
                WorkspaceMember.role == Role.OWNER.value,
                WorkspaceMember.status == "active",
            )
        )
        if (owners or 0) <= 1:
            raise ValidationError("A workspace must always have at least one owner.")
    member.role = role.value
    session.add(member)
    await session.flush()
    return member


async def remove_member(session: AsyncSession, *, member: WorkspaceMember) -> None:
    """Remove a member from a workspace, protecting the last owner."""
    if member.role == Role.OWNER.value:
        owners = await session.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == member.workspace_id,
                WorkspaceMember.role == Role.OWNER.value,
                WorkspaceMember.status == "active",
            )
        )
        if (owners or 0) <= 1:
            raise ValidationError("A workspace must always have at least one owner.")
    await session.delete(member)


__all__ = [
    "add_member",
    "change_member_role",
    "create_workspace",
    "get_workspace_for_member",
    "list_members",
    "list_workspaces_for_user",
    "member_counts",
    "remove_member",
    "slugify",
]
