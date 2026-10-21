"""Row Level Security behaviour, exercised as the ``authenticated`` role.

RLS is the second authorization layer behind the API (AGENTS.md 4A.6). These
tests connect as the schema owner, temporarily grant privileges to the
``authenticated`` role inside a transaction, switch role, and assert the
policies themselves - so a policy regression fails the build even if the API
happens to enforce the rule correctly.

Everything is rolled back at the end of each test: the grants and the role
switch never leak.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = [pytest.mark.integration, pytest.mark.security]

FIRST = {
    "email": "rls-first@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "RLS First",
}
SECOND = {
    "email": "rls-second@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "RLS Second",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed(client, register_user) -> tuple[dict, dict, str, str]:
    first = await register_user(FIRST)
    second = await register_user(SECOND)
    alpha = await client.post(
        "/api/v1/workspaces", json={"name": "Alpha"}, headers=_auth(first["access_token"])
    )
    beta = await client.post(
        "/api/v1/workspaces", json={"name": "Beta"}, headers=_auth(second["access_token"])
    )
    assert alpha.status_code == 201, alpha.text
    assert beta.status_code == 201, beta.text
    return first, second, alpha.json()["id"], beta.json()["id"]


async def _become_authenticated(session, user_id: str) -> None:  # type: ignore[no-untyped-def]
    """Grant table access for the test transaction, then act as the user's JWT."""
    await session.execute(text("grant usage on schema app to authenticated"))
    await session.execute(
        text("grant select, insert, update, delete on all tables in schema app to authenticated")
    )
    await session.execute(
        text("select set_config('request.jwt.claim.sub', :sub, true)"),
        {"sub": str(user_id)},
    )
    await session.execute(text("set local role authenticated"))


class TestWorkspaceVisibility:
    async def test_member_sees_only_their_workspaces(
        self, client, session_factory, register_user
    ) -> None:
        first, _second, alpha, beta = await _seed(client, register_user)

        async with session_factory() as session:
            await _become_authenticated(session, first["user"]["id"])
            visible = (
                (await session.execute(text("select id::text from app.workspaces"))).scalars().all()
            )
            assert set(visible) == {alpha}
            assert beta not in set(visible)
            await session.rollback()

    async def test_membership_rows_are_scoped(self, client, session_factory, register_user) -> None:
        first, _second, alpha, beta = await _seed(client, register_user)

        async with session_factory() as session:
            await _become_authenticated(session, first["user"]["id"])
            rows = (
                (
                    await session.execute(
                        text("select workspace_id::text from app.workspace_members")
                    )
                )
                .scalars()
                .all()
            )
            assert set(rows) == {alpha}
            assert beta not in set(rows)
            await session.rollback()

    async def test_profiles_are_visible_only_to_self_without_a_shared_workspace(
        self, client, session_factory, register_user
    ) -> None:
        first, _second, _alpha, _beta = await _seed(client, register_user)

        async with session_factory() as session:
            await _become_authenticated(session, first["user"]["id"])
            visible = (
                (await session.execute(text("select id::text from app.profiles"))).scalars().all()
            )
            assert visible == [first["user"]["id"]]
            await session.rollback()


class TestMutationGuards:
    async def test_ownership_cannot_be_reassigned_through_rls(
        self, client, session_factory, register_user
    ) -> None:
        _first, second, alpha, _beta = await _seed(client, register_user)

        async with session_factory() as session:
            await _become_authenticated(session, _first["user"]["id"])
            with pytest.raises(DBAPIError) as excinfo:
                await session.execute(
                    text(
                        "update app.workspaces set owner_id = :owner, name = 'Hijacked' "
                        "where id = :id"
                    ),
                    {"owner": second["user"]["id"], "id": alpha},
                )
            assert "row-level security" in str(excinfo.value).lower()
            await session.rollback()

    async def test_audit_events_are_visible_only_to_workspace_admins(
        self, client, session_factory, register_user
    ) -> None:
        first, second, alpha, beta = await _seed(client, register_user)

        async with session_factory() as session:
            await _become_authenticated(session, first["user"]["id"])
            visible = (
                (await session.execute(text("select workspace_id::text from app.audit_events")))
                .scalars()
                .all()
            )
            assert set(visible) == {alpha}
            await session.rollback()

        async with session_factory() as session:
            await _become_authenticated(session, second["user"]["id"])
            visible = (
                (await session.execute(text("select workspace_id::text from app.audit_events")))
                .scalars()
                .all()
            )
            assert set(visible) == {beta}
            await session.rollback()


class TestDataApiPosture:
    async def test_authenticated_has_no_grants_by_default(
        self, client, session_factory, register_user
    ) -> None:
        await _seed(client, register_user)

        async with session_factory() as session:
            await session.execute(text("set local role authenticated"))
            with pytest.raises(DBAPIError) as excinfo:
                await session.execute(text("select count(*) from app.workspaces"))
            assert "permission denied" in str(excinfo.value).lower()
            await session.rollback()

    async def test_local_credentials_have_no_policy(
        self, client, session_factory, register_user
    ) -> None:
        await _seed(client, register_user)

        async with session_factory() as session:
            # Grant the schema and the table so the only remaining barrier is
            # Row Level Security itself: `local_credentials` has no policy, so
            # the authenticated role sees nothing even with SELECT granted.
            await session.execute(text("grant usage on schema app to authenticated"))
            await session.execute(text("grant select on app.local_credentials to authenticated"))
            await session.execute(text("set local role authenticated"))
            rows = (
                await session.execute(text("select profile_id from app.local_credentials"))
            ).all()
            assert rows == []
            await session.rollback()
