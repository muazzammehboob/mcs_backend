"""Fireworks AI provider using the OpenAI SDK.

Implements the LLMProvider interface for Fireworks AI.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import logging
from typing import Any

from openai import AsyncOpenAI
import openai

from app.providers.base import ChatResponse, LLMProvider, Message, ModelInfo
from app.providers.exceptions import GeminiAPIError

logger = logging.getLogger(__name__)

_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"


class FireworksProvider(LLMProvider):
    """Adapter for Fireworks AI using the OpenAI Python SDK."""

    def __init__(self, api_key: str) -> None:
        """Initialize with the user's API key.

        Args:
            api_key: The Fireworks API key.
        """
        self._api_key = api_key
        # We instantiate AsyncOpenAI using the Fireworks endpoint
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=_FIREWORKS_BASE_URL,
            timeout=60.0,
        )

    async def chat_completion(
        self,
        system: str,
        messages: list[Message],
        **params: Any,
    ) -> ChatResponse:
        """Send a chat completion request to Fireworks AI."""
        model: str = params.get("model", "accounts/fireworks/models/llama-v3p1-8b-instruct")

        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})

        for m in messages:
            oai_messages.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
        }
        if "temperature" in params and params["temperature"] is not None:
            kwargs["temperature"] = params["temperature"]
        if "top_p" in params and params["top_p"] is not None:
            kwargs["top_p"] = params["top_p"]
        if "max_output_tokens" in params and params["max_output_tokens"] is not None:
            kwargs["max_tokens"] = params["max_output_tokens"]

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except openai.APIError as exc:
            raise GeminiAPIError(
                f"Fireworks API error: {exc}",
                status_code=exc.status_code if hasattr(exc, "status_code") else 502,
            ) from exc
        except Exception as exc:
            raise GeminiAPIError(f"Network error calling Fireworks: {exc}") from exc

        content = response.choices[0].message.content or ""
        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return ChatResponse(content=content, model=model, usage=usage)

    async def chat_completion_stream(
        self,
        system: str,
        messages: list[Message],
        **params: Any,
    ) -> AsyncGenerator[dict, None]:
        """Send a streaming chat completion request to Fireworks AI."""
        model: str = params.get("model", "accounts/fireworks/models/llama-v3p1-8b-instruct")

        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})

        for m in messages:
            oai_messages.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "stream": True,
            # include_usage is useful for fireworks but some compat endpoints use stream_options
            "stream_options": {"include_usage": True},
        }
        if "temperature" in params and params["temperature"] is not None:
            kwargs["temperature"] = params["temperature"]
        if "top_p" in params and params["top_p"] is not None:
            kwargs["top_p"] = params["top_p"]
        if "max_output_tokens" in params and params["max_output_tokens"] is not None:
            kwargs["max_tokens"] = params["max_output_tokens"]

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield {"type": "token", "content": delta.content}

                if hasattr(chunk, "usage") and chunk.usage:
                    yield {
                        "type": "usage",
                        "usage": {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        }
                    }
        except openai.APIError as exc:
            yield {
                "type": "error",
                "message": f"Fireworks API error: {exc}",
                "error_type": "api_error",
            }
        except Exception as exc:
            yield {
                "type": "error",
                "message": f"Network error calling Fireworks: {exc}",
                "error_type": "api_error",
            }

    async def list_models(self) -> list[ModelInfo]:
        """List models available from Fireworks.
        
        Note: The OpenAI SDK provides `self._client.models.list()`.
        """
        try:
            models_response = await self._client.models.list()
            result = []
            for m in models_response.data:
                result.append(ModelInfo(id=m.id, name=m.id))
            return result
        except Exception as exc:
            raise GeminiAPIError(f"Error listing models: {exc}") from exc

    async def count_tokens(self, system: str, messages: list[Message]) -> int:
        """Approximate token count (since Fireworks doesn't have a countTokens endpoint natively).
        
        We'll use a simple character heuristic or tiktoken.
        """
        # A simple fallback heuristic
        total_chars = len(system) + sum(len(m.content) for m in messages)
        return total_chars // 4

    async def close(self) -> None:
        """Close the underlying client."""
        await self._client.close()
