"""Unit tests for the role/permission matrix."""

from __future__ import annotations

import pytest

from app.core.permissions import (
    BASELINE_PERMISSIONS,
    Permission,
    Role,
    permissions_for_role,
    role_has_permission,
)


class TestRoleMatrix:
    def test_owner_has_every_permission(self) -> None:
        for permission in Permission:
            assert role_has_permission(Role.OWNER, permission) is True

    def test_viewer_is_read_only(self) -> None:
        viewer = permissions_for_role(Role.VIEWER)
        assert Permission.RUN_READ in viewer
        assert Permission.AGENT_WRITE not in viewer
        assert Permission.APPROVAL_DECIDE not in viewer
        assert Permission.WORKSPACE_MANAGE_MEMBERS not in viewer

    def test_reviewer_can_decide_approvals_but_not_publish(self) -> None:
        reviewer = permissions_for_role(Role.REVIEWER)
        assert Permission.APPROVAL_DECIDE in reviewer
        assert Permission.AGENT_PUBLISH not in reviewer

    def test_developer_can_build_but_not_manage_members(self) -> None:
        developer = permissions_for_role(Role.DEVELOPER)
        assert Permission.AGENT_WRITE in developer
        assert Permission.WORKFLOW_PUBLISH in developer
        assert Permission.WORKSPACE_MANAGE_MEMBERS not in developer

    def test_admin_can_manage_members_but_not_delete_workspace(self) -> None:
        admin = permissions_for_role(Role.ADMIN)
        assert Permission.WORKSPACE_MANAGE_MEMBERS in admin
        assert Permission.WORKSPACE_DELETE not in admin

    def test_unknown_role_grants_nothing(self) -> None:
        assert permissions_for_role("not-a-role") == frozenset()  # type: ignore[arg-type]

    @pytest.mark.parametrize("role", list(Role))
    def test_every_role_can_read_workspaces(self, role: Role) -> None:
        assert role_has_permission(role, Permission.WORKSPACE_READ) is True

    def test_baseline_permissions_include_workspace_creation(self) -> None:
        assert Permission.WORKSPACE_CREATE in BASELINE_PERMISSIONS
