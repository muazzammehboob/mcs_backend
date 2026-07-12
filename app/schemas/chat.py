"""Pydantic schemas for chat endpoints."""

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single message in the chat request."""

    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    provider: str = "gemini"
    api_key: str | None = None
    system: str = ""
    messages: list[ChatMessage]
    model: str = "gemini-2.5-flash"
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    effort: str | None = None  # low, medium, high, max


class ChatResponseSchema(BaseModel):
    """Response from the chat endpoint."""

    content: str
    model: str
    usage: dict | None = None


from app.schemas.pair import PRPairResponse

class SendMessageRequest(BaseModel):
    provider: str = "gemini"
    api_key: str | None = None
    prompt_text: str
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    effort: str | None = None
    attachment_ids: list[int] | None = None

class SendMessageResponse(PRPairResponse):
    usage: dict
