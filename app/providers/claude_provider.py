"""Concrete Claude adapter using hand-rolled httpx calls to Anthropic.

Implements base LLMProvider interface for Claude models.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging

import httpx

from app.providers.base import ChatResponse, LLMProvider, Message, ModelInfo
from app.providers.exceptions import GeminiAPIError as ClaudeAPIError  # Reuse exception class for simplicity

logger = logging.getLogger(__name__)

_CLAUDE_BASE_URL = "https://api.anthropic.com/v1"


class ClaudeProvider(LLMProvider):
    """Hand-rolled httpx adapter for Anthropic's Claude API."""

    def __init__(self, api_key: str) -> None:
        """Initialize with the API key.

        Args:
            api_key: The API key.
        """
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=_CLAUDE_BASE_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(60.0),
        )

    async def chat_completion(
        self,
        system: str,
        messages: list[Message],
        **params: dict,
    ) -> ChatResponse:
        """Send a chat completion request to Claude.

        Args:
            system: System instruction text.
            messages: Ordered list of user/assistant messages.
            **params: Generation parameters.

        Returns:
            ChatResponse with assistant content.
        """
        model: str = params.get("model", "claude-3-5-sonnet-20241022")  # type: ignore[assignment]
        
        # Build Anthropic body
        body = {
            "model": model,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": params.get("max_output_tokens") or 4096,
        }
        if "temperature" in params and params["temperature"] is not None:
            body["temperature"] = params["temperature"]
        if "top_p" in params and params["top_p"] is not None:
            body["top_p"] = params["top_p"]

        try:
            response = await self._client.post("/messages", json=body)
        except httpx.HTTPError as exc:
            raise ClaudeAPIError(
                f"Network error calling Claude: {exc}",
                status_code=getattr(exc, "status_code", None),
            ) from exc

        if response.status_code >= 400:
            raise ClaudeAPIError(
                f"Claude API error: {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        content = data.get("content", [])
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")

        usage_meta = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_meta.get("input_tokens", 0),
            "completion_tokens": usage_meta.get("output_tokens", 0),
            "total_tokens": usage_meta.get("input_tokens", 0) + usage_meta.get("output_tokens", 0),
        }

        return ChatResponse(content=text, model=model, usage=usage)

    async def chat_completion_stream(
        self,
        system: str,
        messages: list[Message],
        **params: dict,
    ) -> AsyncGenerator[dict, None]:
        """Send a streaming chat completion request to Claude.

        Yields:
            Dict events.
        """
        model: str = params.get("model", "claude-3-5-sonnet-20241022")  # type: ignore[assignment]

        body = {
            "model": model,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": params.get("max_output_tokens") or 4096,
            "stream": True,
        }
        if "temperature" in params and params["temperature"] is not None:
            body["temperature"] = params["temperature"]
        if "top_p" in params and params["top_p"] is not None:
            body["top_p"] = params["top_p"]

        try:
            async with self._client.stream("POST", "/messages", json=body) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise ClaudeAPIError(
                        f"Claude API error: {response.text}",
                        status_code=response.status_code,
                    )

                # Anthropic yields standard server-sent events
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = chunk.get("type")
                        if event_type == "content_block_delta":
                            delta = chunk.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield {"type": "token", "content": text}
                        elif event_type == "message_delta":
                            # Yield token usage metadata from final message_delta event
                            usage_meta = chunk.get("usage", {})
                            if usage_meta:
                                yield {
                                    "type": "usage",
                                    "usage": {
                                        "prompt_tokens": usage_meta.get("input_tokens", 0),
                                        "completion_tokens": usage_meta.get("output_tokens", 0),
                                        "total_tokens": usage_meta.get("input_tokens", 0) + usage_meta.get("output_tokens", 0),
                                    }
                                }
                        elif event_type == "error":
                            yield {
                                "type": "error",
                                "message": chunk.get("error", {}).get("message", "Unknown Claude error"),
                                "error_type": "api_error"
                            }
        except httpx.HTTPError as exc:
            yield {
                "type": "error",
                "message": f"Network error calling Claude: {exc}",
                "error_type": "api_error",
            }
        except Exception as exc:
            yield {
                "type": "error",
                "message": str(exc),
                "error_type": "api_error",
            }

    async def list_models(self) -> list[ModelInfo]:
        """Return static Claude models list."""
        return [
            ModelInfo(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet"),
            ModelInfo(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku"),
        ]

    async def count_tokens(self, system: str, messages: list[Message]) -> int:
        """Estimate token count for Claude (rough estimate: 4 chars/token)."""
        char_count = len(system) + sum(len(m.content) for m in messages)
        return char_count // 4

    async def close(self) -> None:
        """Close the underlying client."""
        await self._client.aclose()
