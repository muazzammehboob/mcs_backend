"""Pydantic schemas for GlobalSettings singleton."""

from pydantic import BaseModel, ConfigDict


class GlobalSettingsUpdate(BaseModel):
    """Request body for updating GlobalSettings."""

    persona: str | None = None
    instructions: str | None = None
    negative_constraints: str | None = None


class GlobalSettingsResponse(BaseModel):
    """Response model for GlobalSettings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    persona: str | None
    instructions: str | None
    negative_constraints: str | None
