from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import GlobalSettings
from app.schemas.global_settings import GlobalSettingsResponse, GlobalSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/global", response_model=GlobalSettingsResponse)
async def get_global_settings(
    db: AsyncSession = Depends(get_db),
) -> GlobalSettings:
    """Get the singleton global settings."""
    result = await db.execute(select(GlobalSettings).order_by(GlobalSettings.id.asc()).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        # Create default if not exists
        settings = GlobalSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.put("/global", response_model=GlobalSettingsResponse)
async def update_global_settings(
    body: GlobalSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> GlobalSettings:
    """Update the singleton global settings."""
    result = await db.execute(select(GlobalSettings).order_by(GlobalSettings.id.asc()).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = GlobalSettings()
        db.add(settings)

    if body.persona is not None:
        settings.persona = body.persona
    if body.instructions is not None:
        settings.instructions = body.instructions
    if body.negative_constraints is not None:
        settings.negative_constraints = body.negative_constraints

    await db.commit()
    await db.refresh(settings)
    return settings
