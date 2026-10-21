"""CRM tools against the explicitly seeded synthetic dataset.

The workspace is isolated: every query is scoped by ``workspace_id`` and the
tests prove a tool cannot read another tenant's rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.errors import ToolExecutionFailed
from app.core.permissions import Permission
from app.models.crm import CrmCustomer, CrmDeal, FollowupDraft
from app.tools import ToolApprovalRequiredError, ToolContext, execute_tool

pytestmark = pytest.mark.integration

OWNER = {
    "email": "crm.owner@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "CRM Owner",
}
OTHER = {
    "email": "crm.other@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Other Owner",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace(client, token: str, name: str) -> dict:
    response = await client.post("/api/v1/workspaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_demo(client, token: str, workspace_id: str) -> dict:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/demo-data", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _context(
    session,
    workspace_id: str,
    permissions: frozenset[Permission] = frozenset(Permission),
) -> ToolContext:
    return ToolContext(
        session=session,
        workspace_id=uuid.UUID(workspace_id),
        actor_id=None,
        run_id=None,
        permissions=permissions,
    )


async def _run(session, workspace_id: str, tool: str, arguments: dict | None = None) -> dict:
    execution = await execute_tool(
        _context(session, workspace_id), tool_name=tool, raw_arguments=arguments or {}
    )
    return execution.output


class TestDemoSeed:
    async def test_demo_seed_is_explicit_idempotent_and_labelled(
        self, client, register_user
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Demo Co")

        first = await _seed_demo(client, auth["access_token"], workspace["id"])
        second = await _seed_demo(client, auth["access_token"], workspace["id"])

        assert first["created"] is True
        assert (first["companies"], first["customers"], first["deals"], first["contacts"]) == (
            5,
            7,
            12,
            5,
        )
        assert second["created"] is False
        assert second["deals"] == 12

        status = await client.get(
            f"/api/v1/workspaces/{workspace['id']}/demo-data",
            headers=_auth(auth["access_token"]),
        )
        assert status.status_code == 200
        assert status.json() == {"seeded": True, "customers": 7, "deals": 12}

    async def test_demo_seed_does_not_touch_other_workspaces(self, client, register_user) -> None:
        first = await register_user(OWNER)
        second = await register_user(OTHER)
        first_ws = await _create_workspace(client, first["access_token"], "First Demo")
        second_ws = await _create_workspace(client, second["access_token"], "Second Demo")

        await _seed_demo(client, first["access_token"], first_ws["id"])

        response = await client.get(
            f"/api/v1/workspaces/{second_ws['id']}/demo-data",
            headers=_auth(second["access_token"]),
        )
        assert response.json() == {"seeded": False, "customers": 0, "deals": 0}


class TestReadTools:
    async def test_search_customers_and_company_join(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Search Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])

        output = await _run(db_session, workspace["id"], "search_customers", {"query": "Aurika"})

        assert output["returned_count"] == 2
        assert {item["name"] for item in output["customers"]} == {"Priya Nair", "Arjun Mehta"}
        assert all(item["company_name"] == "Aurika Logistics" for item in output["customers"])

    async def test_search_deals_applies_value_and_recency_filters(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Deals Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])

        output = await _run(
            db_session,
            workspace["id"],
            "search_deals",
            {"min_amount": 50000, "not_contacted_since_days": 14, "limit": 50},
        )

        assert output["returned_count"] == 7
        assert output["criteria"]["not_contacted_since_days"] == 14
        assert {deal["stage"] for deal in output["deals"]}.isdisjoint({"won", "lost"})
        now = datetime.now(UTC)
        for deal in output["deals"]:
            assert deal["amount"] >= 50000
            contacted = deal["last_contacted_at"]
            assert contacted is None or (now - datetime.fromisoformat(contacted)).days >= 14

    async def test_customer_summary_includes_their_deals(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Summary Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])
        customer_id = await db_session.scalar(
            select(CrmCustomer.id).where(
                CrmCustomer.workspace_id == uuid.UUID(workspace["id"]),
                CrmCustomer.email == "priya.nair@aurika.example",
            )
        )

        output = await _run(
            db_session, workspace["id"], "get_customer_summary", {"customer_id": str(customer_id)}
        )

        assert output["customer"]["name"] == "Priya Nair"
        assert output["deal_count"] == 2
        assert {deal["name"] for deal in output["deals"]} == {
            "Enterprise plan renewal",
            "Onboarding package",
        }

    async def test_deal_details_include_contact_history(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Details Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])
        deal_id = await db_session.scalar(
            select(CrmDeal.id).where(
                CrmDeal.workspace_id == uuid.UUID(workspace["id"]),
                CrmDeal.name == "Enterprise plan renewal",
            )
        )

        output = await _run(
            db_session, workspace["id"], "get_deal_details", {"deal_id": str(deal_id)}
        )

        assert output["deal"]["name"] == "Enterprise plan renewal"
        assert output["customer"]["name"] == "Priya Nair"
        assert len(output["recent_contacts"]) == 1
        assert output["recent_contacts"][0]["channel"] == "email"

    async def test_metrics_and_report_use_persisted_rows(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Metrics Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])

        pipeline = await _run(
            db_session, workspace["id"], "calculate_metrics", {"metric": "pipeline_value"}
        )
        win_rate = await _run(
            db_session, workspace["id"], "calculate_metrics", {"metric": "win_rate"}
        )
        report = await _run(db_session, workspace["id"], "generate_sales_report")

        assert pipeline["value"] is not None and pipeline["value"] > 0
        assert pipeline["sample_size"] > 0
        assert win_rate["value"] == 50.0  # one won, one lost in the demo dataset
        assert win_rate["sample_size"] == 2
        assert report["totals"]["open_deal_count"] > 0
        assert sum(item["deal_count"] for item in report["stage_breakdown"]) == 12

    async def test_knowledge_search_reports_an_explicit_empty_result(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Knowledge Co")

        output = await _run(
            db_session, workspace["id"], "search_knowledge", {"query": "renewal policy"}
        )

        assert output["results"] == []
        assert "No knowledge sources" in output["note"]


class TestWriteTools:
    async def test_followup_draft_is_internal_only(self, client, register_user, db_session) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Draft Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])
        customer_id = await db_session.scalar(
            select(CrmCustomer.id).where(
                CrmCustomer.workspace_id == uuid.UUID(workspace["id"]),
                CrmCustomer.email == "priya.nair@aurika.example",
            )
        )
        deal_id = await db_session.scalar(
            select(CrmDeal.id).where(
                CrmDeal.workspace_id == uuid.UUID(workspace["id"]),
                CrmDeal.name == "Enterprise plan renewal",
            )
        )

        output = await _run(
            db_session,
            workspace["id"],
            "create_followup_draft",
            {
                "customer_id": str(customer_id),
                "deal_id": str(deal_id),
                "channel": "email",
                "subject": "Checking in",
                "body": "Would a short call help?",
            },
        )
        await db_session.commit()

        assert output["status"] == "draft"
        assert output["note"] == "Draft stored internally. Nothing was sent."
        draft = await db_session.get(FollowupDraft, uuid.UUID(output["draft_id"]))
        assert draft is not None
        assert draft.workspace_id == uuid.UUID(workspace["id"])
        assert draft.status == "draft"

    async def test_draft_rejects_a_deal_from_another_customer(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Mismatch Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])
        customer_id = await db_session.scalar(
            select(CrmCustomer.id).where(
                CrmCustomer.workspace_id == uuid.UUID(workspace["id"]),
                CrmCustomer.email == "priya.nair@aurika.example",
            )
        )
        other_deal = await db_session.scalar(
            select(CrmDeal.id).where(
                CrmDeal.workspace_id == uuid.UUID(workspace["id"]),
                CrmDeal.name == "Analytics add-on",
            )
        )

        with pytest.raises(ToolExecutionFailed):
            await _run(
                db_session,
                workspace["id"],
                "create_followup_draft",
                {
                    "customer_id": str(customer_id),
                    "deal_id": str(other_deal),
                    "channel": "email",
                    "subject": "Checking in",
                    "body": "Hello",
                },
            )

    async def test_mark_deal_contacted_never_executes_without_approval(
        self, client, register_user, db_session
    ) -> None:
        auth = await register_user(OWNER)
        workspace = await _create_workspace(client, auth["access_token"], "Approval Co")
        await _seed_demo(client, auth["access_token"], workspace["id"])
        deal = await db_session.scalar(
            select(CrmDeal).where(
                CrmDeal.workspace_id == uuid.UUID(workspace["id"]),
                CrmDeal.name == "Enterprise plan renewal",
            )
        )
        original = deal.last_contacted_at
        deal_id = deal.id

        with pytest.raises(ToolApprovalRequiredError) as excinfo:
            await execute_tool(
                _context(db_session, workspace["id"]),
                tool_name="mark_deal_contacted",
                raw_arguments={"deal_id": str(deal_id), "note": "Spoke to the customer."},
            )

        await db_session.rollback()
        refreshed = await db_session.get(CrmDeal, deal_id)
        assert refreshed is not None
        assert refreshed.last_contacted_at == original
        assert excinfo.value.tool_name == "mark_deal_contacted"


class TestWorkspaceIsolation:
    async def test_tools_never_read_another_workspace(
        self, client, register_user, db_session
    ) -> None:
        first = await register_user(OWNER)
        second = await register_user(OTHER)
        first_ws = await _create_workspace(client, first["access_token"], "Isolated One")
        second_ws = await _create_workspace(client, second["access_token"], "Isolated Two")
        await _seed_demo(client, first["access_token"], first_ws["id"])
        await _seed_demo(client, second["access_token"], second_ws["id"])

        db_session.add(
            CrmCustomer(
                workspace_id=uuid.UUID(second_ws["id"]),
                name="Zeta Isolation Customer",
                email="zeta.isolation@example.com",
                status="prospect",
            )
        )
        await db_session.commit()

        own = await _run(
            db_session, second_ws["id"], "search_customers", {"query": "Zeta Isolation"}
        )
        other = await _run(
            db_session, first_ws["id"], "search_customers", {"query": "Zeta Isolation"}
        )

        assert own["returned_count"] == 1
        assert other["returned_count"] == 0

    async def test_a_customer_id_from_another_workspace_cannot_be_resolved(
        self, client, register_user, db_session
    ) -> None:
        first = await register_user(OWNER)
        second = await register_user(OTHER)
        first_ws = await _create_workspace(client, first["access_token"], "Owner One")
        second_ws = await _create_workspace(client, second["access_token"], "Owner Two")
        await _seed_demo(client, second["access_token"], second_ws["id"])
        foreign_id = await db_session.scalar(
            select(CrmCustomer.id).where(CrmCustomer.workspace_id == uuid.UUID(second_ws["id"]))
        )

        with pytest.raises(ToolExecutionFailed):
            await _run(
                db_session,
                first_ws["id"],
                "get_customer_summary",
                {"customer_id": str(foreign_id)},
            )
