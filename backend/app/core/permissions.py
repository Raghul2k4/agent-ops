"""Role model and permission matrix (`AGENTS.md` §21).

Permissions are enforced **server-side**; the frontend only uses the same
matrix to decide what to render.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Workspace roles, ordered from most to least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Permission(StrEnum):
    """Fine-grained capabilities."""

    WORKSPACE_READ = "workspace.read"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"
    WORKSPACE_MANAGE_MEMBERS = "workspace.manage_members"
    # Granted to every authenticated user regardless of workspace membership:
    # a user must be able to create their first workspace.
    WORKSPACE_CREATE = "workspace.create"

    AGENT_READ = "agent.read"
    AGENT_WRITE = "agent.write"
    AGENT_PUBLISH = "agent.publish"

    WORKFLOW_READ = "workflow.read"
    WORKFLOW_WRITE = "workflow.write"
    WORKFLOW_PUBLISH = "workflow.publish"

    RUN_READ = "run.read"
    RUN_EXECUTE = "run.execute"
    RUN_CANCEL = "run.cancel"

    APPROVAL_READ = "approval.read"
    APPROVAL_DECIDE = "approval.decide"

    PROVIDER_READ = "provider.read"
    PROVIDER_WRITE = "provider.write"

    TOOL_READ = "tool.read"
    TOOL_WRITE = "tool.write"

    EVALUATION_READ = "evaluation.read"
    EVALUATION_WRITE = "evaluation.write"
    EVALUATION_RUN = "evaluation.run"

    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"

    INTEGRATION_READ = "integration.read"
    INTEGRATION_WRITE = "integration.write"

    AUDIT_READ = "audit.read"
    ADMIN_ACCESS = "admin.access"


_VIEWER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.WORKSPACE_CREATE,
        Permission.AGENT_READ,
        Permission.WORKFLOW_READ,
        Permission.RUN_READ,
        Permission.APPROVAL_READ,
        Permission.PROVIDER_READ,
        Permission.TOOL_READ,
        Permission.EVALUATION_READ,
        Permission.KNOWLEDGE_READ,
        Permission.INTEGRATION_READ,
    }
)

_REVIEWER_PERMISSIONS: frozenset[Permission] = frozenset(
    _VIEWER_PERMISSIONS
    | {
        Permission.APPROVAL_DECIDE,
        Permission.RUN_EXECUTE,
        Permission.RUN_CANCEL,
    }
)

_OPERATOR_PERMISSIONS: frozenset[Permission] = frozenset(
    _REVIEWER_PERMISSIONS
    | {
        Permission.KNOWLEDGE_WRITE,
    }
)

_DEVELOPER_PERMISSIONS: frozenset[Permission] = frozenset(
    _OPERATOR_PERMISSIONS
    | {
        Permission.AGENT_WRITE,
        Permission.AGENT_PUBLISH,
        Permission.WORKFLOW_WRITE,
        Permission.WORKFLOW_PUBLISH,
        Permission.TOOL_WRITE,
        Permission.PROVIDER_WRITE,
        Permission.EVALUATION_WRITE,
        Permission.EVALUATION_RUN,
        Permission.INTEGRATION_WRITE,
    }
)

_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(
    _DEVELOPER_PERMISSIONS
    | {
        Permission.WORKSPACE_UPDATE,
        Permission.WORKSPACE_MANAGE_MEMBERS,
        Permission.AUDIT_READ,
        Permission.ADMIN_ACCESS,
    }
)

_OWNER_PERMISSIONS: frozenset[Permission] = frozenset(
    _ADMIN_PERMISSIONS | {Permission.WORKSPACE_DELETE}
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _OWNER_PERMISSIONS,
    Role.ADMIN: _ADMIN_PERMISSIONS,
    Role.DEVELOPER: _DEVELOPER_PERMISSIONS,
    Role.OPERATOR: _OPERATOR_PERMISSIONS,
    Role.REVIEWER: _REVIEWER_PERMISSIONS,
    Role.VIEWER: _VIEWER_PERMISSIONS,
}


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Return whether a role grants a permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for_role(role: Role) -> frozenset[Permission]:
    """Return the full permission set granted to a role."""
    return ROLE_PERMISSIONS.get(role, frozenset())


#: Permissions that every authenticated session carries, independent of membership.
BASELINE_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.WORKSPACE_CREATE,
        Permission.WORKSPACE_READ,
    }
)


__all__ = [
    "BASELINE_PERMISSIONS",
    "ROLE_PERMISSIONS",
    "Permission",
    "Role",
    "permissions_for_role",
    "role_has_permission",
]
