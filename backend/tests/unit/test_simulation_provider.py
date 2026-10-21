"""The labelled simulation provider behaves like a script, never like an LLM."""

from __future__ import annotations

import json
import uuid

from app.providers.base import ChatMessage, ModelRequest, ToolSpec
from app.providers.simulation import SIMULATION_PREFIX, SimulationProvider

DEAL_TOOL = ToolSpec(
    name="search_deals", description="Search deals", input_schema={"type": "object"}
)
DRAFT_TOOL = ToolSpec(
    name="create_followup_draft", description="Draft", input_schema={"type": "object"}
)
CUSTOMER_TOOL = ToolSpec(
    name="search_customers", description="Customers", input_schema={"type": "object"}
)
MARK_TOOL = ToolSpec(
    name="mark_deal_contacted", description="Mark contacted", input_schema={"type": "object"}
)

DEAL_RESULT = {
    "deals": [
        {
            "deal_id": str(uuid.uuid4()),
            "name": "Enterprise plan renewal",
            "customer_id": str(uuid.uuid4()),
            "customer_name": "Priya Nair",
            "amount": 125000,
            "currency": "INR",
            "stage": "negotiation",
            "days_since_contact": 21,
        }
    ],
    "count": 1,
}


async def test_deal_request_produces_structured_filter_arguments() -> None:
    provider = SimulationProvider()
    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=[
                ChatMessage(
                    role="user",
                    content=(
                        "Find deals worth more than ₹50,000 that have not been contacted "
                        "in the last 14 days."
                    ),
                )
            ],
            tools=[DEAL_TOOL, DRAFT_TOOL],
        )
    )

    assert response.finish_reason == "tool_calls"
    assert response.content is None
    assert response.tool_calls[0].name == "search_deals"
    assert response.tool_calls[0].arguments["min_amount"] == 50000.0
    assert response.tool_calls[0].arguments["not_contacted_since_days"] == 14


async def test_after_deal_results_it_proposes_one_internal_draft() -> None:
    provider = SimulationProvider()
    messages = [
        ChatMessage(role="user", content="Find deals over ₹50,000 to follow up."),
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": "sim_call_1",
                    "name": "search_deals",
                    "arguments": {"min_amount": 50000},
                }
            ],
        ),
        ChatMessage(
            role="tool",
            content=json.dumps(DEAL_RESULT),
            tool_call_id="sim_call_1",
            tool_name="search_deals",
        ),
    ]

    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=messages,
            tools=[DEAL_TOOL, DRAFT_TOOL],
        )
    )

    assert response.finish_reason == "tool_calls"
    call = response.tool_calls[0]
    assert call.name == "create_followup_draft"
    assert call.arguments["customer_id"] == DEAL_RESULT["deals"][0]["customer_id"]
    assert call.arguments["deal_id"] == DEAL_RESULT["deals"][0]["deal_id"]
    assert call.arguments["channel"] == "email"


async def test_final_summary_is_prefixed_and_reports_only_tool_output() -> None:
    provider = SimulationProvider()
    messages = [
        ChatMessage(role="user", content="Find deals over ₹50,000 to follow up."),
        ChatMessage(
            role="tool",
            content=json.dumps(DEAL_RESULT),
            tool_name="search_deals",
        ),
        ChatMessage(
            role="tool",
            content=json.dumps({"draft_id": str(uuid.uuid4()), "status": "draft"}),
            tool_name="create_followup_draft",
        ),
    ]

    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=messages,
            tools=[DEAL_TOOL, DRAFT_TOOL],
        )
    )

    assert response.content is not None
    assert response.content.startswith(SIMULATION_PREFIX)
    assert "Enterprise plan renewal" in response.content
    assert "nothing was sent" in response.content
    assert response.finish_reason == "stop"


async def test_empty_result_is_reported_honestly() -> None:
    provider = SimulationProvider()
    messages = [
        ChatMessage(role="user", content="Find deals over ₹5,000,000 to follow up."),
        ChatMessage(role="tool", content='{"deals": [], "count": 0}', tool_name="search_deals"),
    ]

    response = await provider.chat(
        ModelRequest(model="simulation-deterministic", messages=messages, tools=[DEAL_TOOL])
    )

    assert response.content is not None
    assert response.content.startswith(
        f"{SIMULATION_PREFIX} No deals matched the supplied criteria"
    )


async def test_customer_search_is_supported() -> None:
    provider = SimulationProvider()
    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=[ChatMessage(role="user", content="Find customers in Aurika")],
            tools=[CUSTOMER_TOOL],
        )
    )

    assert response.tool_calls[0].name == "search_customers"
    assert "Aurika" in (response.tool_calls[0].arguments["query"] or "")


async def test_unmatched_requests_state_the_limitation() -> None:
    provider = SimulationProvider()
    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=[ChatMessage(role="user", content="Write me a poem about Kubernetes")],
            tools=[DEAL_TOOL],
        )
    )

    assert response.tool_calls == []
    assert response.content is not None
    assert response.content.startswith(SIMULATION_PREFIX)
    assert "No scripted action matched" in response.content


async def test_output_is_deterministic() -> None:
    provider = SimulationProvider()
    request = ModelRequest(
        model="simulation-deterministic",
        messages=[ChatMessage(role="user", content="Find deals above 50000 to follow up")],
        tools=[DEAL_TOOL],
    )

    first = await provider.chat(request)
    second = await provider.chat(request)

    assert first.tool_calls == second.tool_calls
    assert first.usage == second.usage


async def test_a_contact_request_proposes_the_write_tool_for_approval() -> None:
    """The scripted write path exists so the approval gate is reachable."""
    provider = SimulationProvider()
    messages = [
        ChatMessage(
            role="user",
            content="Find the top deal and mark it as contacted after the call.",
        ),
        ChatMessage(
            role="tool",
            content=json.dumps(DEAL_RESULT),
            tool_call_id="sim_call_1",
            tool_name="search_deals",
        ),
    ]

    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=messages,
            tools=[DEAL_TOOL, MARK_TOOL],
        )
    )

    assert response.finish_reason == "tool_calls"
    call = response.tool_calls[0]
    assert call.name == "mark_deal_contacted"
    assert call.arguments["deal_id"] == DEAL_RESULT["deals"][0]["deal_id"]
    assert "contact" in call.arguments["note"].lower()


async def test_the_contact_request_ignores_a_workspace_without_the_write_tool() -> None:
    provider = SimulationProvider()
    messages = [
        ChatMessage(role="user", content="Mark the deal as contacted."),
        ChatMessage(
            role="tool",
            content=json.dumps(DEAL_RESULT),
            tool_call_id="sim_call_1",
            tool_name="search_deals",
        ),
    ]

    response = await provider.chat(
        ModelRequest(
            model="simulation-deterministic",
            messages=messages,
            tools=[DEAL_TOOL, DRAFT_TOOL],
        )
    )

    assert all(call.name != "mark_deal_contacted" for call in response.tool_calls)


def test_capabilities_are_explicit() -> None:
    capabilities = SimulationProvider().capabilities("simulation-deterministic")

    assert capabilities.supports_tools is True
    assert capabilities.supports_streaming is False
    assert capabilities.supports_structured_output is False
