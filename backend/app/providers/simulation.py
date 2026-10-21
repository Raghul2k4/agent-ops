"""Deterministic scripted provider used for demos when no model is available.

This is **not** a language model and never pretends to be one. It follows a
small, documented script over the real tool contracts, and every response is
prefixed with ``[SIMULATED]``. Results it reports come from tool output, never
from invented data (AGENTS.md section 29).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.providers.base import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    ModelUsage,
    ProviderCapabilities,
)

SIMULATION_PREFIX = "[SIMULATED]"

_AMOUNT_RE = re.compile(
    r"(?:over|above|worth more than|greater than|>)\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
    re.I,
)
_DAYS_RE = re.compile(r"(\d+)\s*days?", re.I)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _estimate_tokens(text: str | None) -> int:
    return max(1, len(text or "") // 4) if text else 0


class SimulationProvider:
    """Rule-based provider: useful for a labelled demo, never for evaluation."""

    provider_type = "simulation"

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_structured_output=False,
            supports_streaming=False,
            context_window=8192,
        )

    async def health_check(self) -> tuple[bool, str | None]:
        return True, None

    async def list_models(self) -> list[str]:
        return ["simulation-deterministic"]

    async def chat(self, request: ModelRequest) -> ModelResponse:
        user_text = next(
            (m.content or "" for m in reversed(request.messages) if m.role == "user"), ""
        )
        tool_names = {tool.name for tool in request.tools}
        tool_messages = [m for m in request.messages if m.role == "tool"]
        already_called = {m.tool_name for m in tool_messages}

        call, final = self._plan(user_text, tool_names, tool_messages, already_called)
        if call is not None:
            content = None
            calls = [call]
            finish_reason = "tool_calls"
        else:
            content = f"{SIMULATION_PREFIX} {final}"
            calls = []
            finish_reason = "stop"

        prompt_chars = sum(len(m.content or "") for m in request.messages)
        return ModelResponse(
            content=content,
            tool_calls=calls,
            finish_reason=finish_reason,
            usage=ModelUsage(
                input_tokens=max(1, prompt_chars // 4),
                output_tokens=_estimate_tokens(content) + (20 if calls else 0),
            ),
            model=request.model or "simulation-deterministic",
        )

    # -- script ---------------------------------------------------------
    def _plan(
        self,
        text: str,
        tool_names: set[str],
        tool_messages: list[ChatMessage],
        already_called: set[str | None],
    ) -> tuple[ModelToolCall | None, str]:
        lowered = text.lower()

        if (
            "search_deals" in tool_names
            and "search_deals" not in already_called
            and any(word in lowered for word in ("deal", "pipeline", "follow-up", "follow up"))
        ):
            arguments: dict[str, object] = {}
            amount = _AMOUNT_RE.search(text)
            if amount:
                arguments["min_amount"] = float(amount.group(1).replace(",", ""))
            days = _DAYS_RE.search(text)
            arguments["not_contacted_since_days"] = int(days.group(1)) if days else 14
            arguments["limit"] = 10
            return (
                ModelToolCall(
                    id="sim_call_1",
                    name="search_deals",
                    arguments=arguments,
                ),
                "",
            )

        deals = self._tool_payload(tool_messages, "search_deals")
        if (
            deals is not None
            and "create_followup_draft" in tool_names
            and "create_followup_draft" not in already_called
        ):
            items = deals.get("deals") or []
            if items:
                first = items[0]
                body = (
                    f"Hi {first.get('customer_name', 'there')},\n\n"
                    f"I wanted to follow up on {first.get('name', 'our conversation')}. "
                    "Would a short call this week be useful?\n\n"
                    "Regards,\nSales Operations"
                )
                return (
                    ModelToolCall(
                        id="sim_call_2",
                        name="create_followup_draft",
                        arguments={
                            "customer_id": first.get("customer_id"),
                            "deal_id": first.get("deal_id"),
                            "channel": "email",
                            "subject": f"Following up on {first.get('name', 'our deal')}",
                            "body": body,
                        },
                    ),
                    "",
                )

        if (
            "search_customers" in tool_names
            and "search_customers" not in already_called
            and "customer" in lowered
        ):
            query = re.sub(
                r"^(find|search|show me|list)\s+(all\s+)?(customers?|accounts?)\s*",
                "",
                text.strip(),
                flags=re.I,
            ).strip(" .?!")
            return (
                ModelToolCall(
                    id="sim_call_1",
                    name="search_customers",
                    arguments={"query": query[:120] or None, "limit": 10},
                ),
                "",
            )

        if deals is not None:
            items = deals.get("deals") or []
            if not items:
                return None, "No deals matched the supplied criteria in the CRM data."
            draft = self._tool_payload(tool_messages, "create_followup_draft")
            lines = [
                f"{len(items)} deal(s) matched. Top result: {items[0].get('name')} "
                f"for {items[0].get('customer_name')} ({items[0].get('amount')} "
                f"{items[0].get('currency')}, stage {items[0].get('stage')})."
            ]
            if draft:
                lines.append(
                    f"Draft {draft.get('draft_id')} was created: it is internal only and "
                    "nothing was sent."
                )
            lines.append("Review the proposed actions before deciding what to send.")
            return None, " ".join(lines)

        customers = self._tool_payload(tool_messages, "search_customers")
        if customers is not None:
            count = len(customers.get("customers") or [])
            return None, f"{count} customer(s) matched the query in the CRM data."

        if any(m.role == "tool" for m in tool_messages):
            return None, "Tool execution finished. Review the trace for the returned data."

        return None, (
            "No scripted action matched this request. The simulation provider supports "
            "deal follow-up and customer search demos against the synthetic CRM data."
        )

    @staticmethod
    def _tool_payload(messages: list[ChatMessage], name: str) -> dict[str, Any] | None:
        for message in reversed(messages):
            if message.role == "tool" and message.tool_name == name and message.content:
                try:
                    payload = json.loads(message.content)
                except json.JSONDecodeError:
                    return None
                return payload if isinstance(payload, dict) else None
        return None


__all__ = ["SIMULATION_PREFIX", "SimulationProvider"]
