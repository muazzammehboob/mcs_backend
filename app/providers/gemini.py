"""Concrete Gemini adapter using hand-rolled httpx calls.

Implements consolidated spec §6 (Gemini API Surface), §7 (Message-Shape Mapping),
§11 (Effort dial), §16 (Failed Request / Retry UX), §17 (Safety handling).

All Gemini-specific remapping happens ONLY in this module:
  - assistant -> model role rename
  - content: str -> parts: [{text: ...}]
  - system -> systemInstruction (top-level, not in contents array)
  - x-goog-api-key header (never ?key= query param)
  - v1beta API version

Zero retry/backoff — fail fast on all errors per spec §15.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging

import httpx

from app.providers.base import ChatResponse, LLMProvider, Message, ModelInfo
from app.providers.exceptions import GeminiAPIError, GeminiSafetyBlockError
from app.providers.thinking_map import get_thinking_config

logger = logging.getLogger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    """Hand-rolled httpx adapter for Google's Gemini API."""

    def __init__(self, api_key: str) -> None:
        """Initialize with the user's API key (BYOK, never persisted).

        Args:
            api_key: The Gemini API key from the X-Gemini-Api-Key header.
        """
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=_GEMINI_BASE_URL,
            headers={"x-goog-api-key": api_key},
            timeout=httpx.Timeout(60.0),
        )

    async def chat_completion(
        self,
        system: str,
        messages: list[Message],
        **params: dict,  # type: ignore[override]
    ) -> ChatResponse:
        """Send a chat completion request to Gemini.

        Args:
            system: System instruction text.
            messages: Ordered list of user/assistant messages.
            **params: Supported keys:
                - model (str): Model name, e.g. "gemini-2.5-flash".
                - temperature (float): Sampling temperature.
                - top_p (float): Nucleus sampling parameter.
                - max_output_tokens (int): Maximum output tokens.
                - effort (str): One of "low", "medium", "high", "max".

        Returns:
            ChatResponse with assistant content.

        Raises:
            GeminiSafetyBlockError: If the response was blocked for safety.
            GeminiAPIError: On any API error (4xx, 5xx, network, malformed).
        """
        model: str = params.get("model", "gemini-2.5-flash")  # type: ignore[assignment]

        # Build Gemini request body
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [_to_gemini_content(m) for m in messages],
            "generationConfig": _build_generation_config(params),
        }

        # Add thinking config if the model supports it
        effort: str | None = params.get("effort")  # type: ignore[assignment]
        if effort:
            thinking_cfg = get_thinking_config(model, effort)
            if thinking_cfg and "thinkingConfig" in thinking_cfg:
                body["generationConfig"]["thinkingConfig"] = thinking_cfg["thinkingConfig"]

        # Validate: never both thinkingBudget and thinkingLevel
        tc = body.get("generationConfig", {}).get("thinkingConfig", {})
        if "thinkingBudget" in tc and "thinkingLevel" in tc:
            raise GeminiAPIError(
                "Both thinkingBudget and thinkingLevel are set — "
                "this is a 400 error with Gemini. Check thinking_map.py.",
            )

        url = f"/models/{model}:generateContent"

        try:
            response = await self._client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise GeminiAPIError(
                f"Network error calling Gemini: {exc}",
                status_code=getattr(exc, "status_code", None),
            ) from exc

        if response.status_code >= 400:
            _raise_api_error(response)

        data = response.json()

        # Check for safety block or empty response
        candidates = data.get("candidates", [])
        if not candidates:
            # Check for promptFeedback (prompt blocked before generation)
            feedback = data.get("promptFeedback", {})
            block_reason = feedback.get("blockReason")
            if block_reason:
                ratings = feedback.get("safetyRatings", [])
                raise GeminiSafetyBlockError(
                    f"Prompt blocked: {block_reason}",
                    finish_reason=block_reason,
                    safety_ratings=ratings,
                )
            raise GeminiAPIError("No candidates in Gemini response")

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")

        if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
            ratings = candidate.get("safetyRatings", [])
            raise GeminiSafetyBlockError(
                f"Response blocked: {finish_reason}",
                finish_reason=finish_reason,
                safety_ratings=ratings,
            )

        # Extract content
        content_parts = candidate.get("content", {}).get("parts", [])
        text = ""
        for part in content_parts:
            if "text" in part:
                text += part["text"]

        usage_meta = data.get("usageMetadata", {})
        usage = {
            "prompt_tokens": usage_meta.get("promptTokenCount", 0),
            "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
            "total_tokens": usage_meta.get("totalTokenCount", 0),
        }

        return ChatResponse(content=text, model=model, usage=usage)

    async def chat_completion_stream(
        self,
        system: str,
        messages: list[Message],
        **params: dict,
    ) -> AsyncGenerator[dict, None]:
        """Send a streaming chat completion request to Gemini.

        Yields:
            Dict events of type 'token', 'usage', or 'error'.
        """
        model: str = params.get("model", "gemini-2.5-flash")  # type: ignore[assignment]

        # Build Gemini request body
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [_to_gemini_content(m) for m in messages],
            "generationConfig": _build_generation_config(params),
        }

        # Add thinking config if the model supports it
        effort: str | None = params.get("effort")  # type: ignore[assignment]
        if effort:
            thinking_cfg = get_thinking_config(model, effort)
            if thinking_cfg and "thinkingConfig" in thinking_cfg:
                body["generationConfig"]["thinkingConfig"] = thinking_cfg["thinkingConfig"]

        # Validate: never both thinkingBudget and thinkingLevel
        tc = body.get("generationConfig", {}).get("thinkingConfig", {})
        if "thinkingBudget" in tc and "thinkingLevel" in tc:
            raise GeminiAPIError(
                "Both thinkingBudget and thinkingLevel are set — "
                "this is a 400 error with Gemini. Check thinking_map.py.",
            )

        url = f"/models/{model}:streamGenerateContent?alt=sse"

        try:
            async with self._client.stream("POST", url, json=body) as response:
                if response.status_code >= 400:
                    await response.aread()
                    _raise_api_error(response)

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        chunk = json.loads(data_str)

                        # Check for safety block or empty response
                        candidates = chunk.get("candidates", [])
                        if not candidates:
                            # Check for promptFeedback (prompt blocked before generation)
                            feedback = chunk.get("promptFeedback", {})
                            block_reason = feedback.get("blockReason")
                            if block_reason:
                                ratings = feedback.get("safetyRatings", [])
                                yield {
                                    "type": "error",
                                    "message": f"Prompt blocked: {block_reason}",
                                    "error_type": "safety_block",
                                    "finish_reason": block_reason,
                                    "safety_ratings": ratings,
                                }
                                return
                            continue

                        candidate = candidates[0]
                        finish_reason = candidate.get("finishReason")

                        if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                            ratings = candidate.get("safetyRatings", [])
                            yield {
                                "type": "error",
                                "message": f"Response blocked: {finish_reason}",
                                "error_type": "safety_block",
                                "finish_reason": finish_reason,
                                "safety_ratings": ratings,
                            }
                            return

                        # Extract content
                        content_parts = candidate.get("content", {}).get("parts", [])
                        text = ""
                        for part in content_parts:
                            if "text" in part:
                                text += part["text"]

                        if text:
                            yield {"type": "token", "content": text}

                        usage_meta = chunk.get("usageMetadata")
                        if usage_meta:
                            yield {
                                "type": "usage",
                                "usage": {
                                    "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                                    "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                                    "total_tokens": usage_meta.get("totalTokenCount", 0),
                                }
                            }
        except httpx.HTTPError as exc:
            yield {
                "type": "error",
                "message": f"Network error calling Gemini: {exc}",
                "error_type": "api_error",
            }
        except GeminiAPIError as exc:
            yield {
                "type": "error",
                "message": exc.message,
                "error_type": "api_error",
            }

    async def list_models(self) -> list[ModelInfo]:
        """Fetch models from Gemini and filter to generateContent-capable ones.

        Returns:
            List of ModelInfo for models that support generateContent.

        Raises:
            GeminiAPIError: On API error.
        """
        try:
            response = await self._client.get("/models")
        except httpx.HTTPError as exc:
            raise GeminiAPIError(f"Network error listing models: {exc}") from exc

        if response.status_code >= 400:
            _raise_api_error(response)

        data = response.json()
        models: list[ModelInfo] = []

        for m in data.get("models", []):
            supported = m.get("supportedGenerationMethods", [])
            if "generateContent" in supported:
                models.append(ModelInfo(id=m["name"], name=m["displayName"]))

        return models

    async def count_tokens(self, system: str, messages: list[Message]) -> int:
        """Call Gemini's countTokens endpoint.

        Args:
            system: System instruction text.
            messages: Ordered list of user/assistant messages.

        Returns:
            The totalTokenCount from Gemini's response.

        Raises:
            GeminiAPIError: On API error.
        """
        model = "gemini-2.5-flash"  # Default; caller can override
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [_to_gemini_content(m) for m in messages],
        }

        url = f"/models/{model}:countTokens"

        try:
            response = await self._client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise GeminiAPIError(f"Network error counting tokens: {exc}") from exc

        if response.status_code >= 400:
            _raise_api_error(response)

        data = response.json()
        return int(data.get("totalTokens", 0))

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()


def _to_gemini_content(message: Message) -> dict:
    """Convert a generic Message to Gemini's content format.

    Consolidated spec §7:
      - role: assistant -> model
      - content: str -> parts: [{text: ...}]
    """
    gemini_role = "model" if message.role == "assistant" else message.role
    return {
        "role": gemini_role,
        "parts": [{"text": message.content}],
    }


def _build_generation_config(params: dict) -> dict:
    """Build Gemini generationConfig from provider-agnostic params."""
    cfg: dict[str, float | int] = {}
    if "temperature" in params:
        cfg["temperature"] = params["temperature"]
    if "top_p" in params:
        cfg["topP"] = params["top_p"]
    if "max_output_tokens" in params:
        cfg["maxOutputTokens"] = params["max_output_tokens"]
    return cfg


def _raise_api_error(response: httpx.Response) -> None:
    """Parse a Gemini error response and raise the appropriate exception."""
    try:
        data = response.json()
        error_info = data.get("error", {})
        code = error_info.get("code", "")
        message = error_info.get("message", response.text)
        status = error_info.get("status", "")
    except Exception:
        message = response.text or f"HTTP {response.status_code}"
        code = ""
        status = ""

    raise GeminiAPIError(
        message=message,
        provider_error_code=str(code) if code else None,
        status_code=response.status_code,
    )
