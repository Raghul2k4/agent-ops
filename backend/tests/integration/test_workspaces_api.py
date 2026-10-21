"""Integration tests for workspaces, membership and tenant isolation."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

FIRST_USER = {
    "email": "owner@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Owner One",
}
SECOND_USER = {
    "email": "outsider@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Outside Two",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace(client, token: str, name: str) -> dict:
    response = await client.post("/api/v1/workspaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _add_member(client, token: str, workspace_id: str, email: str, role: str) -> dict:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": email, "role": role},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestWorkspaceLifecycle:
    async def test_create_workspace_makes_the_caller_owner(self, client, register_user) -> None:
        auth = await register_user(FIRST_USER)
        body = await _create_workspace(client, auth["access_token"], "Acme Revenue")

        assert body["name"] == "Acme Revenue"
        assert body["slug"] == "acme-revenue"
        assert body["role"] == "owner"
        assert body["owner_id"] == auth["user"]["id"]
        assert body["member_count"] == 1

    async def test_list_is_scoped_to_membership(self, client, register_user) -> None:
        first = await register_user(FIRST_USER)
        second = await register_user(SECOND_USER)
        created = await _create_workspace(client, first["access_token"], "First Co")

        mine = await client.get("/api/v1/workspaces", headers=_auth(first["access_token"]))
        theirs = await client.get("/api/v1/workspaces", headers=_auth(second["access_token"]))

        assert [workspace["id"] for workspace in mine.json()] == [created["id"]]
        assert theirs.json() == []

    async def test_me_includes_memberships(self, client, register_user) -> None:
        auth = await register_user(FIRST_USER)
        created = await _create_workspace(client, auth["access_token"], "Visible Co")

        response = await client.get("/api/v1/me", headers=_auth(auth["access_token"]))

        assert response.status_code == 200
        assert [workspace["id"] for workspace in response.json()["workspaces"]] == [created["id"]]
        assert response.json()["workspaces"][0]["role"] == "owner"

    async def test_workspace_names_must_not_be_blank(self, client, register_user) -> None:
        auth = await register_user(FIRST_USER)
        response = await client.post(
            "/api/v1/workspaces", json={"name": "   "}, headers=_auth(auth["access_token"])
        )
        assert response.status_code == 422

    async def test_unauthenticated_access_is_rejected(self, client) -> None:
        response = await client.get("/api/v1/workspaces")
        assert response.status_code == 401


class TestTenantIsolation:
    async def test_non_member_cannot_read_or_update_a_workspace(
        self, client, register_user
    ) -> None:
        first = await register_user(FIRST_USER)
        second = await register_user(SECOND_USER)
        workspace = await _create_workspace(client, first["access_token"], "Private Co")

        read = await client.get(
            f"/api/v1/workspaces/{workspace['id']}", headers=_auth(second["access_token"])
        )
        update = await client.patch(
            f"/api/v1/workspaces/{workspace['id']}",
            json={"name": "Hijacked"},
            headers=_auth(second["access_token"]),
        )
        members = await client.get(
            f"/api/v1/workspaces/{workspace['id']}/members",
            headers=_auth(second["access_token"]),
        )

        assert read.status_code == 404
        assert update.status_code == 404
        assert members.status_code == 404
        assert read.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    async def test_unknown_workspace_is_not_found(self, client, register_user) -> None:
        auth = await register_user(FIRST_USER)
        response = await client.get(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000000",
            headers=_auth(auth["access_token"]),
        )
        assert response.status_code == 404


class TestMembership:
    async def test_owner_adds_a_member(self, client, register_user) -> None:
        first = await register_user(FIRST_USER)
        second = await register_user(SECOND_USER)
        workspace = await _create_workspace(client, first["access_token"], "Shared Co")

        member = await _add_member(
            client, first["access_token"], workspace["id"], SECOND_USER["email"], "developer"
        )
        assert member["email"] == SECOND_USER["email"]
        assert member["role"] == "developer"

        listed = await client.get(
            f"/api/v1/workspaces/{workspace['id']}/members",
            headers=_auth(first["access_token"]),
        )
        assert {entry["email"] for entry in listed.json()} == {
            FIRST_USER["email"],
            SECOND_USER["email"],
        }

        second_list = await client.get("/api/v1/workspaces", headers=_auth(second["access_token"]))
        assert [entry["id"] for entry in second_list.json()] == [workspace["id"]]
        assert second_list.json()[0]["role"] == "developer"

    async def test_adding_an_unknown_email_is_not_found(self, client, register_user) -> None:
        auth = await register_user(FIRST_USER)
        workspace = await _create_workspace(client, auth["access_token"], "Solo Co")
        response = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/members",
            json={"email": "missing@example.com", "role": "viewer"},
            headers=_auth(auth["access_token"]),
        )
        assert response.status_code == 404

    async def test_duplicate_membership_conflicts(self, client, register_user) -> None:
        first = await register_user(FIRST_USER)
        await register_user(SECOND_USER)
        workspace = await _create_workspace(client, first["access_token"], "Dupe Co")
        await _add_member(
            client, first["access_token"], workspace["id"], SECOND_USER["email"], "viewer"
        )

        response = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/members",
            json={"email": SECOND_USER["email"], "role": "viewer"},
            headers=_auth(first["access_token"]),
        )
        assert response.status_code == 409

    async def test_viewer_cannot_update_or_manage_members(self, client, register_user) -> None:
        first = await register_user(FIRST_USER)
        second = await register_user(SECOND_USER)
        workspace = await _create_workspace(client, first["access_token"], "Locked Co")
        await _add_member(
            client, first["access_token"], workspace["id"], SECOND_USER["email"], "viewer"
        )

        update = await client.patch(
            f"/api/v1/workspaces/{workspace['id']}",
            json={"name": "Viewer Rename"},
            headers=_auth(second["access_token"]),
        )
        add = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/members",
            json={"email": FIRST_USER["email"], "role": "viewer"},
            headers=_auth(second["access_token"]),
        )

        assert update.status_code == 403
        assert add.status_code == 403
        assert update.json()["error"]["code"] == "PERMISSION_DENIED"

    async def test_admin_in_one_workspace_cannot_edit_another(self, client, register_user) -> None:
        """Permissions must be evaluated per workspace, not as a global union."""
        owner = await register_user(FIRST_USER)
        third = await register_user(
            {"email": "third@example.com", "password": "Sup3rSecret!2026", "display_name": "Third"}
        )

        theirs = await _create_workspace(client, third["access_token"], "Third Co")
        await _create_workspace(client, owner["access_token"], "Owner Co")
        # The owner is only a viewer in `third`'s workspace.
        await _add_member(
            client, third["access_token"], theirs["id"], FIRST_USER["email"], "viewer"
        )

        response = await client.patch(
            f"/api/v1/workspaces/{theirs['id']}",
            json={"name": "Not Allowed"},
            headers=_auth(owner["access_token"]),
        )
        assert response.status_code == 403

    async def test_last_owner_cannot_be_removed_or_demoted(self, client, register_user) -> None:
        auth = await register_user(FIRST_USER)
        workspace = await _create_workspace(client, auth["access_token"], "Owned Co")
        members = await client.get(
            f"/api/v1/workspaces/{workspace['id']}/members",
            headers=_auth(auth["access_token"]),
        )
        membership_id = next(entry["id"] for entry in members.json() if entry["role"] == "owner")

        demote = await client.patch(
            f"/api/v1/workspaces/{workspace['id']}/members/{membership_id}",
            json={"role": "viewer"},
            headers=_auth(auth["access_token"]),
        )
        remove = await client.delete(
            f"/api/v1/workspaces/{workspace['id']}/members/{membership_id}",
            headers=_auth(auth["access_token"]),
        )

        assert demote.status_code == 422
        assert remove.status_code == 422
