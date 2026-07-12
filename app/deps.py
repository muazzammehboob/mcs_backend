"""FastAPI dependency functions.

Implements consolidated spec §5 (BYOK & Key Handling).
The header name is exactly ``X-Gemini-Api-Key`` — not configurable in
Milestone 0 so it is structurally impossible to bypass later.
"""

from fastapi import Header, HTTPException, status


BYOK_HEADER_NAME: str = "X-Gemini-Api-Key"


def get_gemini_api_key(
    x_gemini_api_key: str | None = Header(None, alias=BYOK_HEADER_NAME),
) -> str:
    """Extract and validate the Gemini API key from the BYOK header.

    Every LLM-calling endpoint imports this dependency. It raises 401 if the
    header is absent and is never read from a server-side .env or config file.

    Args:
        x_gemini_api_key: The API key sent in the X-Gemini-Api-Key header.

    Returns:
        The validated API key string.

    Raises:
        HTTPException(401): If the header is missing or empty.
    """
    if not x_gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing required header: {BYOK_HEADER_NAME}",
        )
    return x_gemini_api_key


def get_gemini_api_key_optional(
    x_gemini_api_key: str | None = Header(None, alias=BYOK_HEADER_NAME),
) -> str | None:
    """Extract the Gemini API key from the BYOK header if present.

    Does not raise an exception if the header is missing.
    """
    return x_gemini_api_key

