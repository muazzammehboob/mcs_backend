"""Provider-specific exception classes.

Implements consolidated spec §16 (Failed Request / Retry UX) and §17
(Safety-Blocked / Empty Response Handling).

No bare excepts — these are the distinct exception types the API layer
catches to decide HTTP status codes and error payloads.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all provider-related errors."""

    def __init__(
        self,
        message: str,
        provider_error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider_error_code = provider_error_code


class GeminiAPIError(ProviderError):
    """Gemini API returned a non-2xx response or malformed payload.

    Attributes:
        message: Human-readable error description.
        provider_error_code: The error code from Gemini's response, if any.
        status_code: The HTTP status code from the failed call.
    """

    def __init__(
        self,
        message: str,
        provider_error_code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, provider_error_code)
        self.status_code = status_code


class GeminiSafetyBlockError(ProviderError):
    """Gemini blocked the response for safety reasons.

    Consolidated spec §17: carries the actual finishReason and per-category
    safety ratings so the UI can show *why* it was blocked.

    Attributes:
        message: Human-readable description.
        finish_reason: The finishReason from Gemini (e.g., 'SAFETY', 'RECITATION').
        safety_ratings: List of per-category safety rating dicts.
    """

    def __init__(
        self,
        message: str,
        finish_reason: str,
        safety_ratings: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.finish_reason = finish_reason
        self.safety_ratings = safety_ratings or []
