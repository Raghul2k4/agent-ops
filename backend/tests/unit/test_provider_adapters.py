"""Provider adapters: wire-format translation and failure normalisation.

Every adapter is exercised through ``httpx.MockTransport`` so the tests are
hermetic: no network, no API key, no paid provider.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.models.providers import ModelProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.base import (
    ChatMessage,
    ModelRequest,
    ProviderError,
    ProviderFailure,
    ToolSpec,
)
from app.providers.factory import build_provider, resolve_secret
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

TOOLS = [
    ToolSpec(
        name="search_deals",
        description="Search deals",
        input_schema={"type": "object", "properties": {"min_amount": {"type": "number"}}},
    )
]


def _request(**overrides: object) -> ModelRequest:
    payload: dict[str, object] = {
        "model": "test-model",
        "messages": [
            ChatMessage(role="system", content="You are a CRM assistant."),
            ChatMessage(role="user", content="Find deals."),
        ],
        "tools": TOOLS,
        "temperature": 0.1,
        "max_output_tokens": 256,
    }
    payload.update(overrides)
    return ModelRequest.model_validate(payload)


def _transport(handler) -> httpx.MockTransport:  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


async def test_openai_compatible_parses_tool_calls_and_usage() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "test-model",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_deals",
                                        "arguments": '{"min_amount": 50000}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7},
            },
        )

    provider = OpenAICompatibleProvider(
        "https://llm.example/v1",
        api_key="test-key",
        transport=_transport(handler),
    )
    response = await provider.chat(_request())

    assert captured["path"] == "/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["tools"][0]["function"]["name"] == "search_deals"
    assert response.content is None
    assert response.finish_reason == "tool_calls"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 7
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].arguments == {"min_amount": 50000}


async def test_openai_compatible_rejects_malformed_tool_arguments() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "search_deals",
                                        "arguments": "{not json",
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    provider = OpenAICompatibleProvider("https://llm.example/v1", transport=_transport(handler))
    response = await provider.chat(_request())

    assert response.tool_calls[0].arguments == {}


async def test_openai_compatible_maps_auth_and_rate_limit_failures() -> None:
    for status, expected in (
        (401, ProviderFailure.AUTHENTICATION),
        (429, ProviderFailure.RATE_LIMITED),
    ):

        async def handler(request: httpx.Request, status: int = status) -> httpx.Response:
            return httpx.Response(status, json={"error": {"message": "no"}})

        provider = OpenAICompatibleProvider("https://llm.example/v1", transport=_transport(handler))
        with pytest.raises(ProviderError) as excinfo:
            await provider.chat(_request())

        assert excinfo.value.failure == expected
        assert str(excinfo.value.status_code) == str(status)
        assert excinfo.value.retryable is (expected == ProviderFailure.RATE_LIMITED)


async def test_openai_compatible_health_check_reports_unreachable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = OpenAICompatibleProvider("https://llm.example/v1", transport=_transport(handler))
    healthy, message = await provider.health_check()

    assert healthy is False
    assert message is not None and "unreachable" in message.lower()


async def test_ollama_parses_tool_calls_and_usage() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_deals",
                                "arguments": {"min_amount": 1000},
                            }
                        }
                    ],
                },
                "done": True,
                "prompt_eval_count": 9,
                "eval_count": 4,
            },
        )

    provider = OllamaProvider("http://ollama.example:11434", transport=_transport(handler))
    response = await provider.chat(_request(model="llama3.1"))

    assert captured["path"] == "/api/chat"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.1
    assert response.usage.input_tokens == 9
    assert response.usage.output_tokens == 4
    assert response.tool_calls[0].name == "search_deals"
    assert response.finish_reason == "tool_calls"


async def test_ollama_list_models() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.1"}, {"name": "qwen2.5"}]})

    provider = OllamaProvider("http://ollama.example:11434", transport=_transport(handler))

    assert await provider.list_models() == ["llama3.1", "qwen2.5"]


async def test_anthropic_translates_messages_and_tool_calls() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-test",
                "content": [
                    {"type": "text", "text": "Looking that up."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "search_deals",
                        "input": {"min_amount": 2000},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 15, "output_tokens": 6},
            },
        )

    provider = AnthropicProvider(
        "https://anthropic.example/v1",
        api_key="test-key",
        transport=_transport(handler),
    )
    response = await provider.chat(_request(model="claude-test"))

    assert captured["path"] == "/v1/messages"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["system"] == "You are a CRM assistant."
    assert body["messages"] == [{"role": "user", "content": "Find deals."}]
    assert body["tools"][0]["input_schema"]["type"] == "object"
    assert response.content == "Looking that up."
    assert response.finish_reason == "tool_use"
    assert response.tool_calls[0].arguments == {"min_amount": 2000}
    assert response.usage.input_tokens == 15


async def test_anthropic_rejects_a_non_list_content_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "not-a-list"})

    provider = AnthropicProvider("https://anthropic.example/v1", transport=_transport(handler))

    with pytest.raises(ProviderError) as excinfo:
        await provider.chat(_request())

    assert excinfo.value.failure == ProviderFailure.INVALID_RESPONSE


def test_factory_builds_simulation_without_credentials() -> None:
    provider = ModelProvider(provider_type="simulation", display_name="Demo")

    adapter = build_provider(provider)

    assert adapter.provider_type == "simulation"


def test_factory_requires_base_url_for_unknown_provider() -> None:
    provider = ModelProvider(provider_type="anthropic", display_name="A", base_url=None)
    # Anthropic has a default base URL, so force the unsupported branch instead.
    provider.provider_type = "custom"

    with pytest.raises(ProviderError) as excinfo:
        build_provider(provider)

    assert excinfo.value.failure == ProviderFailure.UNAVAILABLE


def test_factory_reports_missing_environment_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTOPS_TEST_LLM_KEY", raising=False)
    provider = ModelProvider(
        provider_type="openai_compatible",
        display_name="Cloud",
        secret_reference="AGENTOPS_TEST_LLM_KEY",
    )

    with pytest.raises(ProviderError) as excinfo:
        build_provider(provider)

    assert excinfo.value.failure == ProviderFailure.AUTHENTICATION
    assert "AGENTOPS_TEST_LLM_KEY" in str(excinfo.value)


def test_resolve_secret_reads_environment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOPS_TEST_LLM_KEY", "super-secret-value")
    provider = ModelProvider(
        provider_type="openai_compatible",
        display_name="Cloud",
        secret_reference="AGENTOPS_TEST_LLM_KEY",
    )

    assert resolve_secret(provider) == "super-secret-value"
    assert "super-secret-value" not in str(provider.__dict__)
