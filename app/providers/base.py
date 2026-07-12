"""Abstract base class for LLM providers.

Implements consolidated spec §7 (Message-Shape Mapping — the generic interface).
All provider-specific remapping happens only inside the concrete adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass


@dataclass
class Message:
    """A single message in the generic conversation format."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class ChatResponse:
    """Generic chat completion response."""

    content: str
    model: str
    usage: dict | None = None  # e.g., {"prompt_tokens": N, "completion_tokens": M}


@dataclass
class ModelInfo:
    """Information about a model available from the provider."""

    id: str
    name: str
    supported_modalities: list[str] | None = None


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    The ABC is provider-agnostic. All Gemini-specific remapping happens
    only inside gemini_provider.py.
    """

    @abstractmethod
    async def chat_completion(
        self,
        system: str,
        messages: list[Message],
        **params: dict,
    ) -> ChatResponse:
        """Send a chat completion request.

        Args:
            system: The system instruction text.
            messages: Ordered list of user/assistant messages.
            **params: Provider-agnostic generation parameters
                (temperature, top_p, max_output_tokens, effort, model).

        Returns:
            A ChatResponse with the assistant's content.
        """

    @abstractmethod
    def chat_completion_stream(
        self,
        system: str,
        messages: list[Message],
        **params: dict,
    ) -> AsyncGenerator[dict, None]:
        """Send a streaming chat completion request.

        Yields:
            A dict containing:
                - type: str ("token", "usage", "error")
                - content: str (if type is "token")
                - usage: dict (if type is "usage", keys: prompt_tokens, completion_tokens, total_tokens)
                - message: str (if type is "error")
        """

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return models available from this provider that support chat completion."""

    @abstractmethod
    async def count_tokens(self, system: str, messages: list[Message]) -> int:
        """Count tokens in the given conversation payload.

        Args:
            system: System instruction text.
            messages: Ordered list of user/assistant messages.

        Returns:
            The token count as reported by the provider.
        """
