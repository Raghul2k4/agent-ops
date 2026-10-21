"""OpenAI-compatible chat-completions adapter.

Works with OpenAI and the many providers exposing the same wire format (Groq,
Together, OpenRouter, vLLM, LM Studio). The API key is read from a server-side
environment variable named by ``secret_reference`` and is never persisted.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.base import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    ModelUsage,
    ProviderCapabilities,
    ProviderError,
    ProviderFailure,
)


def _messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {"role": message.role, "content": message.content or ""}
        if message.role == "tool":
            item["tool_call_id"] = message.tool_call_id or ""
            if message.tool_name:
                item["name"] = message.tool_name
        if message.role == "assistant" and message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in message.tool_calls
            ]
            if not message.content:
                item["content"] = None
        converted.append(item)
    return converted


class OpenAICompatibleProvider:
    provider_type = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        supports_tools: bool = True,
        supports_structured_output: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._supports_tools = supports_tools
        self._supports_structured_output = supports_structured_output

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=self._supports_tools,
            supports_structured_output=self._supports_structured_output,
            supports_streaming=True,
            context_window=None,
        )

    def _client(self) -> httpx.AsyncClient:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self._transport,
            headers=headers,
        )

    @staticmethod
    def _map_error(exc: Exception) -> ProviderError:
        if isinstance(exc, httpx.TimeoutException):
            return ProviderError(
                "The model provider timed out.",
                failure=ProviderFailure.TIMEOUT,
                retryable=True,
            )
        if isinstance(exc, httpx.ConnectError):
            return ProviderError(
                "The model provider is unreachable.",
                failure=ProviderFailure.UNAVAILABLE,
                retryable=True,
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (401, 403):
                return ProviderError(
                    "The model provider rejected the configured credential.",
                    failure=ProviderFailure.AUTHENTICATION,
                    status_code=status,
                )
            if status == 429:
                return ProviderError(
                    "The model provider is rate limiting requests.",
                    failure=ProviderFailure.RATE_LIMITED,
                    retryable=True,
                    status_code=status,
                )
            return ProviderError(
                f"The model provider returned HTTP {status}.",
                failure=ProviderFailure.INVALID_RESPONSE,
                status_code=status,
            )
        return ProviderError("The model provider response could not be processed.")

    async def health_check(self) -> tuple[bool, str | None]:
        try:
            async with self._client() as client:
                response = await client.get("/models")
                response.raise_for_status()
            return True, None
        except Exception as exc:
            return False, self._map_error(exc).message

    async def list_models(self) -> list[str]:
        try:
            async with self._client() as client:
                response = await client.get("/models")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise self._map_error(exc) from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ProviderError(
                "The provider returned an unexpected model list.",
                failure=ProviderFailure.INVALID_RESPONSE,
            )
        return [str(item["id"]) for item in data if isinstance(item, dict) and item.get("id")]

    async def chat(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": _messages(request.messages),
        }
        if request.tools and self._supports_tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
            ]
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.structured_output and self._supports_structured_output:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": request.structured_output,
            }

        try:
            async with self._client() as client:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._map_error(exc) from exc

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ProviderError(
                "The provider returned no choices.",
                failure=ProviderFailure.INVALID_RESPONSE,
            )
        message = choices[0].get("message") or {}
        calls: list[ModelToolCall] = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") if isinstance(raw, dict) else None
            if not isinstance(function, dict) or not function.get("name"):
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            calls.append(
                ModelToolCall(
                    id=str(raw.get("id") or f"call_{len(calls)}"),
                    name=str(function["name"]),
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )

        usage = data.get("usage") or {}
        content = message.get("content")
        return ModelResponse(
            content=str(content) if content else None,
            tool_calls=calls,
            finish_reason=str(
                choices[0].get("finish_reason") or ("tool_calls" if calls else "stop")
            ),
            usage=ModelUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
            model=str(data.get("model") or request.model),
        )


__all__ = ["OpenAICompatibleProvider"]
