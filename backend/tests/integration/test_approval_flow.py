"""Approval lifecycle: propose, review, decide, execute.

Every case drives the real API against the real database. The only
substitution is the model transport: a scripted provider proposes a tool call
so the runtime reaches the approval gate deterministically.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.models.crm import CrmContact, CrmDeal
from app.providers.base import (
    ModelResponse,
    ModelToolCall,
    ModelUsage,
    ProviderCapabilities,
)

pytestmark = pytest.mark.integration

OWNER = {
    "email": "approvals.owner@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Approval Owner",
}
VIEWER = {
    "email": "approvals.viewer@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Approval Viewer",
}
OUTSIDER = {
    "email": "approvals.outsider@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Approval Outsider",
}

TERMINAL = ("succeeded", "failed", "cancelled")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class ScriptedToolProvider:
    """Proposes one tool call, then answers with text."""

    provider_type = "simulation"

    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.calls = 0

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True)

    async def health_check(self) -> tuple[bool, str | None]:
        return True, None

    async def list_models(self) -> list[str]:
        return ["approval-script"]

    async def chat(self, request):  # type: ignore[no-untyped-def]
        # The first turn of every conversation proposes the tool; once a tool
        # result is present the model answers with text. This keeps the script
        # correct for a run and for a replay of the same run.
        already_executed = any(message.role == "tool" for message in request.messages)
        if not already_executed:
            return ModelResponse(
                content=None,
                tool_calls=[
                    ModelToolCall(id="scripted_1", name=self.tool_name, arguments=self.arguments)
                ],
                finish_reason="tool_calls",
                usage=ModelUsage(input_tokens=10, output_tokens=5),
                model="approval-script",
            )
        return ModelResponse(
            content="The action completed after approval.",
            finish_reason="stop",
            usage=ModelUsage(input_tokens=8, output_tokens=4),
            model="approval-script",
        )


async def _bootstrap(client, register_user) -> dict:
    auth = await register_user(OWNER)
    token = auth["access_token"]
    workspace = await client.post(
        "/api/v1/workspaces", json={"name": "Approval Co"}, headers=_auth(token)
    )
    assert workspace.status_code == 201, workspace.text
    workspace_id = workspace.json()["id"]
    seeded = await client.post(f"/api/v1/workspaces/{workspace_id}/demo-data", headers=_auth(token))
    assert seeded.status_code == 200, seeded.text
    provider = await client.post(
        f"/api/v1/models/providers/simulation?workspace_id={workspace_id}",
        headers=_auth(token),
    )
    assert provider.status_code == 200, provider.text
    body = provider.json()
    return {
        "token": token,
        "workspace_id": workspace_id,
        "provider": body,
        "model_id": body["models"][0]["id"],
    }


async def _create_agent(client, ctx: dict, *, tool_names: list[str]) -> dict:
    response = await client.post(
        f"/api/v1/agents?workspace_id={ctx['workspace_id']}",
        json={
            "name": "Approval Agent",
            "description": "Proposes a write action that needs a decision.",
            "system_prompt": "Use the CRM tools.",
            "tool_names": tool_names,
            "provider_id": ctx["provider"]["id"],
            "model_config_id": ctx["model_id"],
        },
        headers=_auth(ctx["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _publish(client, ctx: dict, agent_id: str) -> dict:
    response = await client.post(
        f"/api/v1/agents/{agent_id}/publish",
        json={"change_summary": "Initial version"},
        headers=_auth(ctx["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _run(client, ctx: dict, agent_id: str, message: str = "Do the thing.") -> dict:
    response = await client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={"input": {"message": message}},
        headers=_auth(ctx["token"]),
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _wait(
    client,
    token: str,
    run_id: str,
    *,
    stop_at: tuple[str, ...] = (*TERMINAL, "awaiting_approval"),
    wait_seconds: float = 20.0,
) -> dict:
    deadline = time.monotonic() + wait_seconds
    last: dict = {}
    while time.monotonic() < deadline:
        response = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in stop_at:
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach {stop_at}; last status {last.get('status')}")


async def _deal_id(db_session, workspace_id: uuid.UUID) -> str:
    deal = await db_session.scalar(
        select(CrmDeal).where(CrmDeal.workspace_id == workspace_id).limit(1)
    )
    assert deal is not None
    return str(deal.id)


async def _deal_state(db_session, deal_id: str) -> tuple[datetime | None, int]:
    """The contact state of a deal: when it was last contacted and how often."""
    deal = await db_session.scalar(select(CrmDeal).where(CrmDeal.id == uuid.UUID(deal_id)))
    assert deal is not None
    await db_session.refresh(deal)
    contacts = int(
        await db_session.scalar(
            select(func.count())
            .select_from(CrmContact)
            .where(CrmContact.deal_id == uuid.UUID(deal_id))
        )
        or 0
    )
    return deal.last_contacted_at, contacts


async def _pending_approval(client, ctx: dict) -> dict:
    response = await client.get(
        f"/api/v1/approvals?workspace_id={ctx['workspace_id']}&status=pending",
        headers=_auth(ctx["token"]),
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "expected a pending approval request"
    return items[0]


class TestApprovalLifecycle:
    async def test_high_risk_tool_creates_a_request_and_pauses_the_run(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])
        before = await _deal_state(db_session, deal_id)

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            final = await _wait(client, ctx["token"], run["id"])
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        assert final["status"] == "awaiting_approval"
        assert final["pending_approval_id"]

        approval = await _pending_approval(client, ctx)
        assert approval["tool_name"] == "mark_deal_contacted"
        assert approval["risk_level"] == "high"
        assert approval["status"] == "pending"
        assert len(approval["canonical_arguments_hash"]) == 64
        assert approval["arguments"]["deal_id"] == deal_id

        # The business record was not touched.
        assert await _deal_state(db_session, deal_id) == before

    async def test_approving_the_exact_payload_resumes_the_run(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])
        before = await _deal_state(db_session, deal_id)

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            paused = await _wait(client, ctx["token"], run["id"])
            assert paused["status"] == "awaiting_approval"

            approval = await _pending_approval(client, ctx)
            decision = await client.post(
                f"/api/v1/approvals/{approval['id']}/decision",
                json={
                    "decision": "approve",
                    "arguments_hash": approval["canonical_arguments_hash"],
                    "note": "Reviewed and accepted.",
                },
                headers=_auth(ctx["token"]),
            )
            assert decision.status_code == 200, decision.text
            assert decision.json()["approval"]["status"] == "approved"

            final = await _wait(
                client, ctx["token"], run["id"], stop_at=TERMINAL, wait_seconds=25.0
            )
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        assert final["status"] == "succeeded", final
        assert "completed after approval" in (final["output"] or {}).get("message", "")

        after = await _deal_state(db_session, deal_id)
        assert after[1] == before[1] + 1
        assert after[0] != before[0]

    async def test_approving_a_tampered_payload_is_refused(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])
        before = await _deal_state(db_session, deal_id)

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            await _wait(client, ctx["token"], run["id"])
            approval = await _pending_approval(client, ctx)

            tampered = "0" * 64
            decision = await client.post(
                f"/api/v1/approvals/{approval['id']}/decision",
                json={"decision": "approve", "arguments_hash": tampered},
                headers=_auth(ctx["token"]),
            )
            assert decision.status_code == 409, decision.text
            assert decision.json()["error"]["code"] == "APPROVAL_MISMATCH"

            still = await client.get(f"/api/v1/runs/{run['id']}", headers=_auth(ctx["token"]))
            assert still.json()["status"] == "awaiting_approval"
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        assert await _deal_state(db_session, deal_id) == before

    async def test_rejecting_an_approval_ends_the_run_without_executing(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])
        before = await _deal_state(db_session, deal_id)

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            await _wait(client, ctx["token"], run["id"])
            approval = await _pending_approval(client, ctx)

            decision = await client.post(
                f"/api/v1/approvals/{approval['id']}/decision",
                json={
                    "decision": "reject",
                    "arguments_hash": approval["canonical_arguments_hash"],
                    "note": "Do not contact the customer yet.",
                },
                headers=_auth(ctx["token"]),
            )
            assert decision.status_code == 200, decision.text
            assert decision.json()["approval"]["status"] == "rejected"

            final = await _wait(
                client, ctx["token"], run["id"], stop_at=TERMINAL, wait_seconds=25.0
            )
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        assert final["status"] == "failed"
        assert final["error_code"] == "APPROVAL_REJECTED"
        assert await _deal_state(db_session, deal_id) == before

    async def test_expired_approval_cannot_be_decided(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])
        before = await _deal_state(db_session, deal_id)

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            await _wait(client, ctx["token"], run["id"])
            approval = await _pending_approval(client, ctx)

            # Age the request past its expiry window.
            from sqlalchemy import text

            await db_session.execute(
                text(
                    "update app.approval_requests set expires_at = now() - interval '1 minute' "
                    "where id = :approval_id"
                ),
                {"approval_id": uuid.UUID(approval["id"])},
            )
            await db_session.commit()

            decision = await client.post(
                f"/api/v1/approvals/{approval['id']}/decision",
                json={
                    "decision": "approve",
                    "arguments_hash": approval["canonical_arguments_hash"],
                },
                headers=_auth(ctx["token"]),
            )
            assert decision.status_code == 409, decision.text
            assert decision.json()["error"]["code"] == "APPROVAL_EXPIRED"
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        assert await _deal_state(db_session, deal_id) == before

    async def test_a_viewer_cannot_decide_an_approval(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            await _wait(client, ctx["token"], run["id"])
            approval = await _pending_approval(client, ctx)
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        viewer = await register_user(VIEWER)
        await client.post(
            f"/api/v1/workspaces/{ctx['workspace_id']}/members",
            json={"email": VIEWER["email"], "role": "viewer"},
            headers=_auth(ctx["token"]),
        )
        decision = await client.post(
            f"/api/v1/approvals/{approval['id']}/decision",
            json={
                "decision": "approve",
                "arguments_hash": approval["canonical_arguments_hash"],
            },
            headers=_auth(viewer["access_token"]),
        )
        assert decision.status_code == 403, decision.text
        assert decision.json()["error"]["code"] == "PERMISSION_DENIED"

    async def test_another_workspace_cannot_see_or_decide_an_approval(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            await _wait(client, ctx["token"], run["id"])
            approval = await _pending_approval(client, ctx)
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        outsider = await register_user(OUTSIDER)
        listing = await client.get(
            f"/api/v1/approvals?workspace_id={ctx['workspace_id']}",
            headers=_auth(outsider["access_token"]),
        )
        assert listing.status_code == 404, listing.text

        detail = await client.get(
            f"/api/v1/approvals/{approval['id']}", headers=_auth(outsider["access_token"])
        )
        assert detail.status_code == 404, detail.text

        decision = await client.post(
            f"/api/v1/approvals/{approval['id']}/decision",
            json={
                "decision": "approve",
                "arguments_hash": approval["canonical_arguments_hash"],
            },
            headers=_auth(outsider["access_token"]),
        )
        assert decision.status_code == 404, decision.text


class TestPolicyEnforcement:
    async def test_a_blocked_tool_is_refused_by_the_policy(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])

        policy = await client.patch(
            f"/api/v1/policies?workspace_id={ctx['workspace_id']}",
            json={"blocked_tools": ["mark_deal_contacted"]},
            headers=_auth(ctx["token"]),
        )
        assert policy.status_code == 200, policy.text
        assert policy.json()["blocked_tools"] == ["mark_deal_contacted"]

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            final = await _wait(client, ctx["token"], run["id"], stop_at=TERMINAL)
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        assert final["status"] == "failed"
        assert final["error_code"] == "POLICY_VIOLATION"
        assert "not allowed" in (final["error_summary"] or "")

    async def test_the_emergency_pause_blocks_new_runs(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["search_deals"])
        await _publish(client, ctx, agent["id"])

        paused = await client.patch(
            f"/api/v1/policies?workspace_id={ctx['workspace_id']}",
            json={"execution_paused": True, "paused_reason": "Investigating an incident."},
            headers=_auth(ctx["token"]),
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["execution_paused"] is True

        run = await client.post(
            f"/api/v1/agents/{agent['id']}/run",
            json={"input": {"message": "Find deals."}},
            headers=_auth(ctx["token"]),
        )
        assert run.status_code == 403, run.text
        assert run.json()["error"]["code"] == "POLICY_VIOLATION"
        assert "paused" in run.json()["error"]["message"]

    async def test_a_disabled_agent_cannot_run(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["search_deals"])
        await _publish(client, ctx, agent["id"])

        disabled = await client.patch(
            f"/api/v1/policies?workspace_id={ctx['workspace_id']}",
            json={"disabled_agent_ids": [agent["id"]]},
            headers=_auth(ctx["token"]),
        )
        assert disabled.status_code == 200, disabled.text

        run = await client.post(
            f"/api/v1/agents/{agent['id']}/run",
            json={"input": {"message": "Find deals."}},
            headers=_auth(ctx["token"]),
        )
        assert run.status_code == 403, run.text
        assert run.json()["error"]["code"] == "POLICY_VIOLATION"

    async def test_the_workspace_run_quota_is_enforced(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["search_deals"])
        await _publish(client, ctx, agent["id"])

        policy = await client.patch(
            f"/api/v1/policies?workspace_id={ctx['workspace_id']}",
            json={"max_runs_per_hour": 1},
            headers=_auth(ctx["token"]),
        )
        assert policy.status_code == 200, policy.text

        first = await client.post(
            f"/api/v1/agents/{agent['id']}/run",
            json={"input": {"message": "Find deals."}},
            headers=_auth(ctx["token"]),
        )
        assert first.status_code == 202, first.text

        second = await client.post(
            f"/api/v1/agents/{agent['id']}/run",
            json={"input": {"message": "Find more deals."}},
            headers=_auth(ctx["token"]),
        )
        assert second.status_code == 429, second.text
        assert second.json()["error"]["code"] == "RATE_LIMITED"

    async def test_only_an_administrator_may_change_the_policy(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        viewer = await register_user(VIEWER)
        await client.post(
            f"/api/v1/workspaces/{ctx['workspace_id']}/members",
            json={"email": VIEWER["email"], "role": "viewer"},
            headers=_auth(ctx["token"]),
        )

        response = await client.patch(
            f"/api/v1/policies?workspace_id={ctx['workspace_id']}",
            json={"execution_paused": True},
            headers=_auth(viewer["access_token"]),
        )
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


class TestReplay:
    async def test_a_replay_links_to_the_source_and_asks_again(
        self, client, register_user, db_session
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx, tool_names=["mark_deal_contacted"])
        await _publish(client, ctx, agent["id"])
        deal_id = await _deal_id(db_session, ctx["workspace_id"])
        before = await _deal_state(db_session, deal_id)

        provider = ScriptedToolProvider(
            "mark_deal_contacted", {"deal_id": deal_id, "note": "Called the customer."}
        )
        import app.runtime.engine as engine

        original = engine.build_provider
        engine.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
        try:
            run = await _run(client, ctx, agent["id"])
            await _wait(client, ctx["token"], run["id"])
            await _pending_approval(client, ctx)

            replay = await client.post(
                f"/api/v1/runs/{run['id']}/replay", headers=_auth(ctx["token"])
            )
            assert replay.status_code == 202, replay.text
            body = replay.json()
            assert body["replay_of_run_id"] == run["id"]
            assert body["replay_mode"] is True

            replayed = await _wait(client, ctx["token"], body["id"])
        finally:
            engine.build_provider = original  # type: ignore[assignment]

        # A replay never repeats the irreversible action on its own.
        assert replayed["status"] == "awaiting_approval"
        approvals = await client.get(
            f"/api/v1/approvals?workspace_id={ctx['workspace_id']}&status=pending",
            headers=_auth(ctx["token"]),
        )
        assert len(approvals.json()["items"]) == 2

        assert await _deal_state(db_session, deal_id) == before
