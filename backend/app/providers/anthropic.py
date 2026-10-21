"""Anthropic Messages API adapter.

The OpenAI-style tool list is translated to Anthropic's ``tools`` format, and
``tool_use`` content blocks become provider-neutral tool calls.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.providers.base import (
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    ModelUsage,
    ProviderCapabilities,
    ProviderError,
    ProviderFailure,
)

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    provider_type = "anthropic"

    def __init__(
        self,
        base_url: str = "https://api.anthropic.com/v1",
        *,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_structured_output=False,
            supports_streaming=True,
            context_window=None,
        )

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
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
                "The Anthropic request timed out.",
                failure=ProviderFailure.TIMEOUT,
                retryable=True,
            )
        if isinstance(exc, httpx.ConnectError):
            return ProviderError(
                "Anthropic is unreachable.",
                failure=ProviderFailure.UNAVAILABLE,
                retryable=True,
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (401, 403):
                return ProviderError(
                    "Anthropic rejected the configured credential.",
                    failure=ProviderFailure.AUTHENTICATION,
                    status_code=status,
                )
            if status == 429:
                return ProviderError(
                    "Anthropic is rate limiting requests.",
                    failure=ProviderFailure.RATE_LIMITED,
                    retryable=True,
                    status_code=status,
                )
            return ProviderError(
                f"Anthropic returned HTTP {status}.",
                failure=ProviderFailure.INVALID_RESPONSE,
                status_code=status,
            )
        return ProviderError("The Anthropic response could not be processed.")

    async def health_check(self) -> tuple[bool, str | None]:
        # There is no unauthenticated ping; a models list call is cheap.
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
                "Anthropic returned an unexpected model list.",
                failure=ProviderFailure.INVALID_RESPONSE,
            )
        return [str(item["id"]) for item in data if isinstance(item, dict) and item.get("id")]

    def _body(self, request: ModelRequest) -> dict[str, Any]:
        system = "\n\n".join(m.content or "" for m in request.messages if m.role == "system")
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.tool_call_id or "",
                                "content": message.content or "",
                            }
                        ],
                    }
                )
            elif message.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                for call in message.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                        }
                    )
                messages.append({"role": "assistant", "content": blocks or message.content or ""})
            elif message.role in ("user", "assistant"):
                messages.append({"role": message.role, "content": message.content or ""})

        body: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens or 1024,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.tools:
            body["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in request.tools
            ]
        return body

    async def chat(self, request: ModelRequest) -> ModelResponse:
        try:
            async with self._client() as client:
                response = await client.post("/messages", json=self._body(request))
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._map_error(exc) from exc

        blocks = data.get("content") if isinstance(data, dict) else None
        if not isinstance(blocks, list):
            raise ProviderError(
                "Anthropic returned no content blocks.",
                failure=ProviderFailure.INVALID_RESPONSE,
            )

        texts: list[str] = []
        calls: list[ModelToolCall] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                texts.append(str(block["text"]))
            if block.get("type") == "tool_use" and block.get("name"):
                calls.append(
                    ModelToolCall(
                        id=str(block.get("id") or f"toolu_{len(calls)}"),
                        name=str(block["name"]),
                        arguments=(
                            block.get("input") if isinstance(block.get("input"), dict) else {}
                        ),
                    )
                )

        usage = data.get("usage") or {}
        return ModelResponse(
            content="\n".join(texts) or None,
            tool_calls=calls,
            finish_reason=str(data.get("stop_reason") or ("tool_calls" if calls else "stop")),
            usage=ModelUsage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ),
            model=str(data.get("model") or request.model),
        )


__all__ = ["AnthropicProvider"]
