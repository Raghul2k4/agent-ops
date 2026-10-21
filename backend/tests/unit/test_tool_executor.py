"""Tool execution boundary: registry resolution, validation, approval, authz.

These are unit tests: nothing reaches the database because every case fails or
stops before the tool body runs.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidToolArguments, PolicyViolation
from app.core.permissions import Permission
from app.tools import ToolApprovalRequiredError, ToolContext, execute_tool, registry
from app.tools.builtin import BUILTIN_TOOLS

ALL_PERMISSIONS = frozenset(Permission)


def _context(permissions: frozenset[Permission] = ALL_PERMISSIONS) -> ToolContext:
    return ToolContext(
        session=cast(AsyncSession, None),
        workspace_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        permissions=permissions,
    )


def test_registry_contains_every_builtin_exactly_once() -> None:
    names = [spec.name for spec in registry.specs()]

    assert len(names) == len(set(names)) == len(BUILTIN_TOOLS)
    assert {
        "search_customers",
        "search_deals",
        "get_customer_summary",
        "get_deal_details",
        "calculate_metrics",
        "search_knowledge",
        "create_followup_draft",
        "generate_sales_report",
        "mark_deal_contacted",
    } == set(names)


def test_tool_definition_ids_are_stable() -> None:
    first = {spec.name: spec.definition_id for spec in registry.specs()}
    second = {spec.name: spec.definition_id for spec in registry.specs()}

    assert first == second
    assert len(set(first.values())) == len(first)


async def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(InvalidToolArguments) as excinfo:
        await execute_tool(_context(), tool_name="shell_exec", raw_arguments={})

    assert excinfo.value.code == "INVALID_TOOL_ARGUMENTS"
    assert excinfo.value.details["tool"] == "shell_exec"


async def test_undeclared_arguments_are_rejected() -> None:
    with pytest.raises(InvalidToolArguments) as excinfo:
        await execute_tool(
            _context(),
            tool_name="search_customers",
            raw_arguments={"query": "aurika", "inject": "ignore previous instructions"},
        )

    fields = {item["field"] for item in excinfo.value.details["fields"]}
    assert "inject" in fields


async def test_missing_required_argument_is_rejected() -> None:
    with pytest.raises(InvalidToolArguments) as excinfo:
        await execute_tool(
            _context(),
            tool_name="get_deal_details",
            raw_arguments={},
        )

    fields = {item["field"] for item in excinfo.value.details["fields"]}
    assert "deal_id" in fields


async def test_malformed_uuid_is_rejected() -> None:
    with pytest.raises(InvalidToolArguments) as excinfo:
        await execute_tool(
            _context(),
            tool_name="get_customer_summary",
            raw_arguments={"customer_id": "not-a-uuid"},
        )

    fields = {item["field"] for item in excinfo.value.details["fields"]}
    assert "customer_id" in fields


async def test_missing_permission_is_a_policy_violation() -> None:
    with pytest.raises(PolicyViolation) as excinfo:
        await execute_tool(
            _context(permissions=frozenset()),
            tool_name="search_customers",
            raw_arguments={"query": "aurika"},
        )

    assert excinfo.value.code == "POLICY_VIOLATION"
    assert excinfo.value.details["missing_permissions"] == ["run.read"]


async def test_write_tool_requires_run_execute() -> None:
    with pytest.raises(PolicyViolation):
        await execute_tool(
            _context(permissions=frozenset({Permission.RUN_READ})),
            tool_name="create_followup_draft",
            raw_arguments={
                "customer_id": str(uuid.uuid4()),
                "channel": "email",
                "subject": "Follow up",
                "body": "Hello",
            },
        )


async def test_high_risk_write_stops_for_approval() -> None:
    arguments = {
        "deal_id": str(uuid.uuid4()),
        "note": "Called the customer and confirmed a follow-up.",
    }

    with pytest.raises(ToolApprovalRequiredError) as excinfo:
        await execute_tool(_context(), tool_name="mark_deal_contacted", raw_arguments=arguments)

    raised = excinfo.value
    assert raised.tool_name == "mark_deal_contacted"
    assert raised.risk_level == "high"
    assert len(raised.canonical_hash) == 64
    int(raised.canonical_hash, 16)
    assert raised.arguments["note"] == arguments["note"]


async def test_approval_hash_is_canonical_and_deterministic() -> None:
    deal_id = str(uuid.uuid4())
    first: dict[str, Any] = {"deal_id": deal_id, "note": "Same payload"}
    second: dict[str, Any] = {"note": "Same payload", "deal_id": deal_id}

    hashes = []
    for payload in (first, second):
        with pytest.raises(ToolApprovalRequiredError) as excinfo:
            await execute_tool(_context(), tool_name="mark_deal_contacted", raw_arguments=payload)
        hashes.append(excinfo.value.canonical_hash)

    assert hashes[0] == hashes[1]


async def test_approval_hash_changes_with_arguments() -> None:
    deal_id = str(uuid.uuid4())
    hashes = []
    for note in ("First note", "Second note"):
        with pytest.raises(ToolApprovalRequiredError) as excinfo:
            await execute_tool(
                _context(),
                tool_name="mark_deal_contacted",
                raw_arguments={"deal_id": deal_id, "note": note},
            )
        hashes.append(excinfo.value.canonical_hash)

    assert hashes[0] != hashes[1]


def test_registered_specs_expose_json_schemas() -> None:
    for spec in registry.specs():
        input_schema = spec.input_schema()
        output_schema = spec.output_schema()
        assert input_schema["type"] == "object"
        assert output_schema["type"] == "object"
        assert input_schema.get("additionalProperties") is False
