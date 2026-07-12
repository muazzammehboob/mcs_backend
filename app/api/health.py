"""Health check endpoint."""

from fastapi import APIRouter, status

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Return 200 OK with no DB dependency."""
    return {"status": "ok"}
