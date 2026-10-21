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


async def _register(client, payload: dict[str, str]) -> dict:
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestWorkspaceLifecycle:
    async def test_create_workspace_makes_the_caller_owner(self, client) -> None:
        await _register(client, FIRST_USER)
        response = await client.post("/api/v1/workspaces", json={"name": "Acme Revenue"})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["name"] == "Acme Revenue"
        assert body["role"] == "owner"
        assert body["slug"].startswith("acme-revenue")
        assert body["member_count"] == 1

    async def test_workspaces_are_listed_for_the_member(self, client) -> None:
        await _register(client, FIRST_USER)
        await client.post("/api/v1/workspaces", json={"name": "First"})
        await client.post("/api/v1/workspaces", json={"name": "Second"})
        response = await client.get("/api/v1/workspaces")
        assert response.status_code == 200
        names = {ws["name"] for ws in response.json()}
        assert names == {"First", "Second"}

    async def test_workspace_can_be_updated(self, client) -> None:
        await _register(client, FIRST_USER)
        created = (await client.post("/api/v1/workspaces", json={"name": "Before"})).json()
        response = await client.patch(
            f"/api/v1/workspaces/{created['id']}", json={"name": "After"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "After"

    async def test_empty_name_is_rejected(self, client) -> None:
        await _register(client, FIRST_USER)
        response = await client.post("/api/v1/workspaces", json={"name": "   "})
        assert response.status_code == 422


class TestMembership:
    async def test_owner_can_add_and_promote_a_member(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Team"})).json()
        member = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/members",
            json={"email": SECOND_USER["email"], "role": "developer"},
        )
        assert member.status_code == 201, member.text
        assert member.json()["role"] == "developer"

        promoted = await client.patch(
            f"/api/v1/workspaces/{workspace['id']}/members/{member.json()['id']}",
            json={"role": "admin"},
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "admin"

    async def test_adding_an_unknown_user_is_not_found(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Team"})).json()
        response = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/members",
            json={"email": "ghost@example.com", "role": "viewer"},
        )
        assert response.status_code == 404

    async def test_duplicate_membership_is_rejected(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Team"})).json()
        body = {"email": SECOND_USER["email"], "role": "viewer"}
        first = await client.post(f"/api/v1/workspaces/{workspace['id']}/members", json=body)
        assert first.status_code == 201
        second = await client.post(f"/api/v1/workspaces/{workspace['id']}/members", json=body)
        assert second.status_code == 409

    async def test_last_owner_cannot_be_demoted(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Team"})).json()
        members = (await client.get(f"/api/v1/workspaces/{workspace['id']}/members")).json()
        owner_membership = members[0]
        response = await client.patch(
            f"/api/v1/workspaces/{workspace['id']}/members/{owner_membership['id']}",
            json={"role": "viewer"},
        )
        assert response.status_code == 422


class TestTenantIsolation:
    async def test_non_member_cannot_read_another_workspace(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Private"})).json()
        await client.post("/api/v1/auth/logout")
        await _register(client, SECOND_USER)

        response = await client.get(f"/api/v1/workspaces/{workspace['id']}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    async def test_non_member_cannot_list_members(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Private"})).json()
        await client.post("/api/v1/auth/logout")
        await _register(client, SECOND_USER)

        response = await client.get(f"/api/v1/workspaces/{workspace['id']}/members")
        assert response.status_code == 404

    async def test_non_member_cannot_update_another_workspace(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Private"})).json()
        await client.post("/api/v1/auth/logout")
        await _register(client, SECOND_USER)

        response = await client.patch(
            f"/api/v1/workspaces/{workspace['id']}", json={"name": "Hijacked"}
        )
        assert response.status_code == 404

    async def test_workspace_ids_are_not_guessable_from_another_tenant(self, client) -> None:
        await _register(client, FIRST_USER)
        workspace = (await client.post("/api/v1/workspaces", json={"name": "Private"})).json()
        await client.post("/api/v1/auth/logout")
        await _register(client, SECOND_USER)

        mine = (await client.get("/api/v1/workspaces")).json()
        assert mine == []
        assert workspace["id"] not in {ws["id"] for ws in mine}
