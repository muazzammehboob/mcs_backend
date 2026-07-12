"""Chat API endpoint.

Implements consolidated spec §5 (BYOK header) and §16 (Failed Request UX).
Uses the GeminiProvider via the abstract LLMProvider interface.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.providers.base import Message
from app.providers.gemini import GeminiProvider
from app.providers.fireworks import FireworksProvider
from app.providers.exceptions import GeminiAPIError, GeminiSafetyBlockError
from app.schemas.chat import ChatRequest, ChatResponseSchema

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completion", response_model=ChatResponseSchema)
async def chat_completion(body: ChatRequest) -> dict:
    """Send a chat completion request to the selected provider.

    The API key is read from the request body.
    """
    api_key = body.api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required api_key in request body",
        )

    if body.provider == "fireworks":
        provider = FireworksProvider(api_key=api_key)
    else:
        provider = GeminiProvider(api_key=api_key)
        
    try:
        messages = [Message(role=m.role, content=m.content) for m in body.messages]

        response = await provider.chat_completion(
            system=body.system,
            messages=messages,
            model=body.model,
            temperature=body.temperature,
            top_p=body.top_p,
            max_output_tokens=body.max_output_tokens,
            effort=body.effort,
        )
        return {
            "content": response.content,
            "model": response.model,
            "usage": response.usage,
        }
    except GeminiSafetyBlockError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "safety_block",
                "finish_reason": exc.finish_reason,
                "safety_ratings": exc.safety_ratings,
                "message": exc.message,
            },
        ) from exc
    except GeminiAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "provider_error",
                "message": exc.message,
                "provider_error_code": exc.provider_error_code,
            },
        ) from exc
    finally:
        await provider.close()
