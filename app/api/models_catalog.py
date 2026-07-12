"""Models catalog endpoint.

Implements consolidated spec §18 (Model Picker).
Live-fetches from Gemini's models.list endpoint using the user's own API key.
"""

from fastapi import APIRouter, Depends

from app.deps import get_gemini_api_key
from app.providers.gemini import GeminiProvider

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models(api_key: str = Depends(get_gemini_api_key)) -> dict:
    """Return models that support generateContent, filtered live from Gemini."""
    provider = GeminiProvider(api_key=api_key)
    try:
        models = await provider.list_models()
        return {
            "models": [
                {"id": m.id, "name": m.name, "modalities": m.supported_modalities}
                for m in models
            ]
        }
    finally:
        await provider.close()
