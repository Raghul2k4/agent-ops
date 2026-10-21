"""Ollama adapter.

Talks to the local Ollama HTTP API (``/api/chat``, ``/api/tags``). Tool calling
is supported only by some models; the adapter forwards the tool list and lets
the model respond without calls when it cannot use them.
"""

from __future__ import annotations

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


def _to_ollama_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {"role": message.role, "content": message.content or ""}
        if message.role == "tool" and message.tool_name:
            item["tool_name"] = message.tool_name
        if message.role == "assistant" and message.tool_calls:
            item["tool_calls"] = [
                {
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ]
        converted.append(item)
    return converted


class OllamaProvider:
    provider_type = "ollama"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        # Ollama itself is unauthenticated; a reverse proxy may require a token.
        self._api_key = api_key

    def capabilities(self, model: str) -> ProviderCapabilities:
        # Conservative: model-specific tool support cannot be discovered
        # reliably before a call, and claiming support that does not exist would
        # silently drop tools.
        return ProviderCapabilities(
            supports_tools=True,
            supports_structured_output=False,
            supports_streaming=True,
            context_window=None,
        )

    def _client(self) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
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
                "The Ollama request timed out.",
                failure=ProviderFailure.TIMEOUT,
                retryable=True,
            )
        if isinstance(exc, httpx.ConnectError):
            return ProviderError(
                (
                    f"Ollama is not reachable at {exc.request.url}"
                    if exc.request
                    else "Ollama is not reachable."
                ),
                failure=ProviderFailure.UNAVAILABLE,
                retryable=True,
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (401, 403):
                return ProviderError(
                    "Ollama rejected the configured credential.",
                    failure=ProviderFailure.AUTHENTICATION,
                    status_code=status,
                )
            if status == 429:
                return ProviderError(
                    "Ollama is rate limiting requests.",
                    failure=ProviderFailure.RATE_LIMITED,
                    retryable=True,
                    status_code=status,
                )
            return ProviderError(
                f"Ollama returned HTTP {status}.",
                failure=ProviderFailure.INVALID_RESPONSE,
                status_code=status,
            )
        return ProviderError("The Ollama response could not be processed.")

    async def health_check(self) -> tuple[bool, str | None]:
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
            return True, None
        except Exception as exc:
            error = self._map_error(exc)
            return False, error.message

    async def list_models(self) -> list[str]:
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise self._map_error(exc) from exc
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ProviderError(
                "Ollama returned an unexpected model list.",
                failure=ProviderFailure.INVALID_RESPONSE,
            )
        return [item["name"] for item in models if isinstance(item, dict) and "name" in item]

    async def chat(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": _to_ollama_messages(request.messages),
            "stream": False,
        }
        if request.tools:
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
        options: dict[str, Any] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        if options:
            payload["options"] = options

        try:
            async with self._client() as client:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._map_error(exc) from exc

        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict):
            raise ProviderError(
                "Ollama returned no message.",
                failure=ProviderFailure.INVALID_RESPONSE,
            )

        calls: list[ModelToolCall] = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = raw.get("function") if isinstance(raw, dict) else None
            if not isinstance(function, dict) or not function.get("name"):
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    import json

                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            calls.append(
                ModelToolCall(
                    id=str(raw.get("id") or f"ollama_call_{index}"),
                    name=str(function["name"]),
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )

        content = message.get("content")
        return ModelResponse(
            content=str(content) if content else None,
            tool_calls=calls,
            finish_reason=str(data.get("done_reason") or ("tool_calls" if calls else "stop")),
            usage=ModelUsage(
                input_tokens=int(data.get("prompt_eval_count") or 0),
                output_tokens=int(data.get("eval_count") or 0),
            ),
            model=str(data.get("model") or request.model),
        )


__all__ = ["OllamaProvider"]
