"""End-to-end API flow for Agent Studio: providers, agents, runs and traces.

Every test drives the real FastAPI app against the real PostgreSQL schema. The
only substitutions are the model transport (the deterministic simulation
provider, which is a first-class labelled provider) and, for two cases, a
scripted in-process provider used to exercise cancellation and approval paths.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from app.providers.base import (
    ModelResponse,
    ModelToolCall,
    ModelUsage,
    ProviderCapabilities,
)

pytestmark = pytest.mark.integration

OWNER = {
    "email": "studio.owner@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Studio Owner",
}
REVIEWER = {
    "email": "studio.reviewer@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Studio Reviewer",
}
OUTSIDER = {
    "email": "studio.outsider@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Studio Outsider",
}

DEMO_REQUEST = (
    "Find deals worth more than INR 50,000 that have not been contacted in the last "
    "14 days. Research the customers, prepare personalized follow-up drafts, and "
    "show me the proposed actions before anything is sent."
)


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


async def _bootstrap(client, register_user) -> dict:
    """Register an owner, create a workspace and ensure the demo provider."""
    auth = await register_user(OWNER)
    workspace = await _create_workspace(client, auth["access_token"], "Studio Co")
    seeded = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/demo-data",
        headers=_auth(auth["access_token"]),
    )
    assert seeded.status_code == 200, seeded.text
    provider = await client.post(
        f"/api/v1/models/providers/simulation?workspace_id={workspace['id']}",
        headers=_auth(auth["access_token"]),
    )
    assert provider.status_code == 200, provider.text
    body = provider.json()
    return {
        "token": auth["access_token"],
        "user": auth["user"],
        "workspace_id": workspace["id"],
        "provider": body,
        "model_id": body["models"][0]["id"],
    }


async def _create_agent(client, ctx: dict, **overrides) -> dict:
    payload: dict = {
        "name": "Sales Operations Assistant",
        "description": "Demo agent for the sales follow-up scenario.",
        "template_key": "sales_followup_drafter",
        "provider_id": ctx["provider"]["id"],
        "model_config_id": ctx["model_id"],
    }
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/agents?workspace_id={ctx['workspace_id']}",
        json=payload,
        headers=_auth(ctx["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _publish(client, ctx: dict, agent_id: str, summary: str = "Initial version") -> dict:
    response = await client.post(
        f"/api/v1/agents/{agent_id}/publish",
        json={"change_summary": summary},
        headers=_auth(ctx["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _run(client, ctx: dict, agent_id: str, message: str) -> dict:
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
    wait_seconds: float = 15.0,
    stop_at=("succeeded", "failed", "cancelled", "awaiting_approval"),
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
    raise AssertionError(f"Run {run_id} did not finish; last status {last.get('status')}")


async def _wait_until_running(client, token: str, run_id: str, wait_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        response = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))
        if response.json()["status"] == "running":
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Run never reached the running state")


class SlowProvider:
    provider_type = "simulation"

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True)

    async def health_check(self) -> tuple[bool, str | None]:
        return True, None

    async def list_models(self) -> list[str]:
        return ["slow-script"]

    async def chat(self, request):  # type: ignore[no-untyped-def]
        await asyncio.sleep(10)
        return ModelResponse(content="too late", finish_reason="stop")


class ApprovalProvider:
    provider_type = "simulation"

    def __init__(self, tool_name: str, arguments: dict) -> None:
        self.tool_name = tool_name
        self.arguments = arguments

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True)

    async def health_check(self) -> tuple[bool, str | None]:
        return True, None

    async def list_models(self) -> list[str]:
        return ["approval-script"]

    async def chat(self, request):  # type: ignore[no-untyped-def]
        return ModelResponse(
            content=None,
            tool_calls=[
                ModelToolCall(id="scripted_1", name=self.tool_name, arguments=self.arguments)
            ],
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            model="approval-script",
        )


class RepeatingToolProvider:
    """Requests the same tool call twice, then answers."""

    provider_type = "simulation"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True)

    async def health_check(self) -> tuple[bool, str | None]:
        return True, None

    async def list_models(self) -> list[str]:
        return ["repeat-script"]

    async def chat(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls <= 2:
            return ModelResponse(
                content=None,
                tool_calls=[
                    ModelToolCall(
                        id=f"repeat_{self.calls}",
                        name="search_deals",
                        arguments={"min_amount": 1000, "limit": 3},
                    )
                ],
                finish_reason="tool_calls",
                usage=ModelUsage(input_tokens=10, output_tokens=5),
                model="repeat-script",
            )
        return ModelResponse(
            content="The same deals were returned; nothing changed.",
            finish_reason="stop",
            usage=ModelUsage(input_tokens=5, output_tokens=2),
            model="repeat-script",
        )


class LoopingToolProvider:
    """Always asks for new tool calls so the tool-call budget is exhausted."""

    provider_type = "simulation"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True)

    async def health_check(self) -> tuple[bool, str | None]:
        return True, None

    async def list_models(self) -> list[str]:
        return ["loop-script"]

    async def chat(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        return ModelResponse(
            content=None,
            tool_calls=[
                ModelToolCall(
                    id=f"loop_{self.calls}_{index}",
                    name="search_deals",
                    arguments={"min_amount": 1000 * (self.calls * 10 + index)},
                )
                for index in range(3)
            ],
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            model="loop-script",
        )


class TestProviders:
    async def test_simulation_provider_is_idempotent_and_secretless(
        self, client, register_user
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        again = await client.post(
            f"/api/v1/models/providers/simulation?workspace_id={ctx['workspace_id']}",
            headers=_auth(ctx["token"]),
        )

        assert again.status_code == 200
        assert again.json()["id"] == ctx["provider"]["id"]
        assert again.json()["provider_type"] == "simulation"
        assert again.json()["secret_reference"] is None
        assert again.json()["has_secret_reference"] is False
        assert len(again.json()["models"]) == 1

    async def test_provider_secret_is_referenced_never_returned(
        self, client, register_user
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        response = await client.post(
            f"/api/v1/models/providers?workspace_id={ctx['workspace_id']}",
            headers=_auth(ctx["token"]),
            json={
                "provider_type": "openai_compatible",
                "display_name": "Cloud LLM",
                "base_url": "https://llm.example/v1",
                "secret_reference": "AGENTOPS_TEST_LLM_KEY",
            },
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["secret_reference"] == "AGENTOPS_TEST_LLM_KEY"
        assert body["has_secret_reference"] is True
        serialized = response.text
        assert "super-secret" not in serialized
        assert "api_key" not in body

    async def test_connection_test_reports_a_missing_server_secret(
        self, client, register_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENTOPS_TEST_LLM_KEY", raising=False)
        ctx = await _bootstrap(client, register_user)
        created = await client.post(
            f"/api/v1/models/providers?workspace_id={ctx['workspace_id']}",
            headers=_auth(ctx["token"]),
            json={
                "provider_type": "openai_compatible",
                "display_name": "Cloud LLM",
                "secret_reference": "AGENTOPS_TEST_LLM_KEY",
            },
        )

        tested = await client.post(
            f"/api/v1/models/providers/{created.json()['id']}/test"
            f"?workspace_id={ctx['workspace_id']}",
            headers=_auth(ctx["token"]),
        )

        assert tested.status_code == 200
        assert tested.json()["ok"] is False
        assert tested.json()["status"] == "error"
        assert "AGENTOPS_TEST_LLM_KEY" in (tested.json()["message"] or "")


class TestAgentStudio:
    async def test_templates_are_functional_configurations(self, client, register_user) -> None:
        auth = await register_user(OWNER)

        response = await client.get("/api/v1/agents/templates", headers=_auth(auth["access_token"]))

        assert response.status_code == 200
        templates = response.json()
        assert len(templates) == 8
        keys = {template["key"] for template in templates}
        assert {"crm_research_assistant", "sales_followup_drafter"} <= keys
        followup = next(t for t in templates if t["key"] == "sales_followup_drafter")
        assert "create_followup_draft" in followup["tool_names"]
        assert followup["system_prompt"].strip()

    async def test_create_update_publish_and_rollback(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx)
        assert agent["current_published_version_id"] is None
        assert agent["draft_configuration"]["model_name"] == "simulation-deterministic"
        original_prompt = agent["draft_configuration"]["system_prompt"]

        first = await _publish(client, ctx, agent["id"], "First publish")
        assert first["version_number"] == 1
        assert first["configuration"]["provider_id"] == ctx["provider"]["id"]

        draft = agent["draft_configuration"]
        draft["system_prompt"] = "Updated instructions for the second version."
        updated = await client.patch(
            f"/api/v1/agents/{agent['id']}",
            json={"draft_configuration": draft, "change_note": "Tighten instructions"},
            headers=_auth(ctx["token"]),
        )
        assert updated.status_code == 200, updated.text
        second = await _publish(client, ctx, agent["id"], "Second publish")
        assert second["version_number"] == 2

        versions = await client.get(
            f"/api/v1/agents/{agent['id']}/versions", headers=_auth(ctx["token"])
        )
        assert [item["version_number"] for item in versions.json()] == [2, 1]
        version_one = next(item for item in versions.json() if item["version_number"] == 1)
        assert version_one["configuration"]["system_prompt"] == original_prompt
        assert version_one["configuration_hash"] == first["configuration_hash"]

        rolled = await client.post(
            f"/api/v1/agents/{agent['id']}/rollback",
            json={"version_id": first["id"]},
            headers=_auth(ctx["token"]),
        )
        assert rolled.status_code == 200
        refreshed = await client.get(f"/api/v1/agents/{agent['id']}", headers=_auth(ctx["token"]))
        assert refreshed.json()["current_version_number"] == 1

    async def test_run_before_publish_is_rejected(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx)

        response = await client.post(
            f"/api/v1/agents/{agent['id']}/run",
            json={"input": {"message": "Find deals to follow up."}},
            headers=_auth(ctx["token"]),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        assert "Publish" in response.json()["error"]["message"]

    async def test_viewer_cannot_publish(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        reviewer = await register_user(REVIEWER)
        await _add_member(client, ctx["token"], ctx["workspace_id"], REVIEWER["email"], "viewer")
        agent = await _create_agent(client, ctx)

        visible = await client.get(
            f"/api/v1/agents/{agent['id']}", headers=_auth(reviewer["access_token"])
        )
        publish = await client.post(
            f"/api/v1/agents/{agent['id']}/publish",
            json={"change_summary": "Nope"},
            headers=_auth(reviewer["access_token"]),
        )

        assert visible.status_code == 200
        assert publish.status_code == 403
        assert publish.json()["error"]["code"] == "PERMISSION_DENIED"

    async def test_cross_workspace_access_is_not_disclosed(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx)
        outsider = await register_user(OUTSIDER)

        item = await client.get(
            f"/api/v1/agents/{agent['id']}", headers=_auth(outsider["access_token"])
        )
        listing = await client.get(
            f"/api/v1/agents?workspace_id={ctx['workspace_id']}",
            headers=_auth(outsider["access_token"]),
        )

        assert item.status_code == 404
        assert listing.status_code == 404


class TestRunsAndTraces:
    async def test_full_sales_operations_demo(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx)
        version = await _publish(client, ctx, agent["id"])

        run = await _run(client, ctx, agent["id"], DEMO_REQUEST)
        assert run["status"] == "queued"
        assert run["agent_version_id"] == version["id"]
        final = await _wait(client, ctx["token"], run["id"])

        assert final["status"] == "succeeded", final
        assert final["completed_at"] is not None
        assert final["duration_ms"] is not None and final["duration_ms"] >= 0
        assert final["error_code"] is None
        output = final["output"]
        assert output["message"].startswith("[SIMULATED]")
        assert "nothing was sent" in output["message"]
        assert output["steps"] == 3
        assert final["token_usage"]["model_calls"] == 3
        assert final["token_usage"]["tool_calls"] == 2
        # The demo provider has no pricing metadata, so cost is unknown, not 0.
        assert final["estimated_cost"] is None

        events = await client.get(f"/api/v1/runs/{run['id']}/events", headers=_auth(ctx["token"]))
        assert events.status_code == 200
        body = events.json()
        types = [item["event_type"] for item in body["items"]]
        sequences = [item["sequence_number"] for item in body["items"]]
        assert sequences == sorted(sequences)
        assert sequences[0] == 1
        assert len(set(sequences)) == len(sequences)
        assert "run.started" in types
        assert "model.request" in types
        assert "model.response" in types
        assert "tool.request" in types
        assert "tool.result" in types
        assert "run.succeeded" in types
        tool_names = [item["payload"].get("tool") for item in body["items"]]
        assert "search_deals" in tool_names
        assert "create_followup_draft" in tool_names

        cursor = await client.get(
            f"/api/v1/runs/{run['id']}/events?after_seq={sequences[2]}",
            headers=_auth(ctx["token"]),
        )
        assert all(item["sequence_number"] > sequences[2] for item in cursor.json()["items"])

        trace = await client.get(f"/api/v1/runs/{run['id']}/trace", headers=_auth(ctx["token"]))
        assert trace.status_code == 200
        spans = trace.json()["spans"]
        span_types = [span["span_type"] for span in spans]
        assert span_types.count("agent_run") == 1
        assert span_types.count("model_call") == 3
        assert span_types.count("tool_call") == 2
        assert all(span["status"] in {"ok", "error", "cancelled"} for span in spans)
        root = next(span for span in spans if span["span_type"] == "agent_run")
        assert all(
            span["parent_span_id"] == root["id"]
            for span in spans
            if span["span_type"] != "agent_run"
        )

        listing = await client.get(
            f"/api/v1/runs?workspace_id={ctx['workspace_id']}", headers=_auth(ctx["token"])
        )
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["id"] == run["id"]

    async def test_repeated_identical_tool_call_is_executed_once(
        self, client, register_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A model that repeats a call must not repeat a side effect."""
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(
            client,
            ctx,
            template_key=None,
            system_prompt="Find matching deals with the CRM tool.",
            tool_names=["search_deals"],
        )
        await _publish(client, ctx, agent["id"])
        monkeypatch.setattr(
            "app.runtime.engine.build_provider", lambda *args, **kwargs: RepeatingToolProvider()
        )

        run = await _run(client, ctx, agent["id"], "Find deals above 1000.")
        final = await _wait(client, ctx["token"], run["id"])

        assert final["status"] == "succeeded", final
        # The identical second call reused the recorded result instead of
        # executing the tool again.
        assert final["token_usage"]["tool_calls"] == 1

        events = await client.get(f"/api/v1/runs/{run['id']}/events", headers=_auth(ctx["token"]))
        types = [item["event_type"] for item in events.json()["items"]]
        assert types.count("tool.request") == 1
        assert types.count("tool.result") == 1
        assert types.count("tool.cached") == 1

    async def test_tool_call_budget_reports_the_work_it_did(
        self, client, register_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bounded run must report what it completed, not an empty result."""
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(
            client,
            ctx,
            template_key=None,
            system_prompt="Find matching deals with the CRM tool.",
            tool_names=["search_deals"],
            limits={
                "max_steps": 8,
                "max_tool_calls": 3,
                "max_wall_clock_seconds": 60,
                "max_total_tokens": 20000,
                "max_cost_usd": 1.0,
            },
        )
        await _publish(client, ctx, agent["id"])
        monkeypatch.setattr(
            "app.runtime.engine.build_provider", lambda *args, **kwargs: LoopingToolProvider()
        )

        run = await _run(client, ctx, agent["id"], "Find deals above 1000.")
        final = await _wait(client, ctx["token"], run["id"])

        assert final["status"] == "failed", final
        assert final["error_code"] == "EXECUTION_LIMIT_EXCEEDED"
        assert "tool-call budget" in (final["error_summary"] or "")
        output = final["output"]
        assert output is not None
        assert output["message"] is None
        assert "tool-call budget" in output["stopped_because"]
        # Every executed call is reported so the operator can see the work.
        assert len(output["completed_actions"]) == 3
        assert all(action["tool"] == "search_deals" for action in output["completed_actions"])
        assert all("output" in action for action in output["completed_actions"])

    async def test_step_budget_is_enforced(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(
            client,
            ctx,
            template_key=None,
            system_prompt="Find matching deals with the CRM tool.",
            tool_names=["search_deals"],
            limits={
                "max_steps": 1,
                "max_tool_calls": 5,
                "max_wall_clock_seconds": 60,
                "max_total_tokens": 20000,
                "max_cost_usd": 1.0,
            },
        )
        await _publish(client, ctx, agent["id"])
        run = await _run(client, ctx, agent["id"], "Find deals above 10000 to follow up.")
        final = await _wait(client, ctx["token"], run["id"])

        assert final["status"] == "failed"
        assert final["error_code"] == "EXECUTION_LIMIT_EXCEEDED"
        assert "steps" in (final["error_summary"] or "")

    async def test_cancellation_stops_an_in_flight_model_call(
        self, client, register_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx)
        await _publish(client, ctx, agent["id"])
        monkeypatch.setattr(
            "app.runtime.engine.build_provider", lambda *args, **kwargs: SlowProvider()
        )

        run = await _run(client, ctx, agent["id"], "Find deals to follow up.")
        await _wait_until_running(client, ctx["token"], run["id"])
        cancelled = await client.post(
            f"/api/v1/runs/{run['id']}/cancel", headers=_auth(ctx["token"])
        )
        assert cancelled.status_code == 200
        final = await _wait(client, ctx["token"], run["id"])

        assert final["status"] == "cancelled"
        assert final["error_code"] == "RUN_CANCELLED"
        events = await client.get(f"/api/v1/runs/{run['id']}/events", headers=_auth(ctx["token"]))
        assert "run.cancelled" in [item["event_type"] for item in events.json()["items"]]

    async def test_high_risk_tool_pauses_for_approval(
        self, client, register_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        deal_id = str(uuid.uuid4())
        agent = await _create_agent(
            client,
            ctx,
            template_key=None,
            system_prompt="Mark the deal as contacted when asked.",
            tool_names=["mark_deal_contacted"],
        )
        await _publish(client, ctx, agent["id"])
        monkeypatch.setattr(
            "app.runtime.engine.build_provider",
            lambda *args, **kwargs: ApprovalProvider(
                "mark_deal_contacted",
                {"deal_id": deal_id, "note": "Scripted approval test."},
            ),
        )

        run = await _run(client, ctx, agent["id"], "Mark that deal as contacted.")
        final = await _wait(client, ctx["token"], run["id"])

        assert final["status"] == "awaiting_approval"
        pending = final["output"]["pending_approval"]
        assert pending["tool"] == "mark_deal_contacted"
        assert pending["risk_level"] == "high"
        assert len(pending["canonical_arguments_hash"]) == 64
        # The approval gate stopped the call before execution, so it must not
        # be reported as an executed tool call.
        assert final["token_usage"]["tool_calls"] == 0
        events = await client.get(f"/api/v1/runs/{run['id']}/events", headers=_auth(ctx["token"]))
        approval = next(
            item for item in events.json()["items"] if item["event_type"] == "approval.required"
        )
        assert approval["event_status"] == "warning"
        assert "not executed" in approval["payload"]["note"]

    async def test_run_access_is_workspace_scoped(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        agent = await _create_agent(client, ctx)
        await _publish(client, ctx, agent["id"])
        run = await _run(client, ctx, agent["id"], "Find deals to follow up.")
        await _wait(client, ctx["token"], run["id"], wait_seconds=20)
        outsider = await register_user(OUTSIDER)

        detail = await client.get(
            f"/api/v1/runs/{run['id']}", headers=_auth(outsider["access_token"])
        )
        events = await client.get(
            f"/api/v1/runs/{run['id']}/events", headers=_auth(outsider["access_token"])
        )
        trace = await client.get(
            f"/api/v1/runs/{run['id']}/trace", headers=_auth(outsider["access_token"])
        )

        assert (detail.status_code, events.status_code, trace.status_code) == (404, 404, 404)


class TestToolRegistryEndpoint:
    async def test_builtin_tools_are_listed_with_contracts_and_risk(
        self, client, register_user
    ) -> None:
        ctx = await _bootstrap(client, register_user)
        response = await client.get(
            f"/api/v1/tools?workspace_id={ctx['workspace_id']}", headers=_auth(ctx["token"])
        )

        assert response.status_code == 200
        tools = {tool["name"]: tool for tool in response.json()}
        assert len(tools) == 9
        assert tools["search_deals"]["risk_level"] == "low"
        assert tools["mark_deal_contacted"]["requires_approval"] is True
        assert tools["mark_deal_contacted"]["risk_level"] == "high"
        assert tools["create_followup_draft"]["requires_approval"] is False
        for tool in tools.values():
            assert tool["input_schema"]["type"] == "object"
            assert tool["is_builtin"] is True

    async def test_cross_workspace_tool_listing_is_denied(self, client, register_user) -> None:
        ctx = await _bootstrap(client, register_user)
        outsider = await register_user(OUTSIDER)

        response = await client.get(
            f"/api/v1/tools?workspace_id={ctx['workspace_id']}",
            headers=_auth(outsider["access_token"]),
        )

        assert response.status_code == 404
