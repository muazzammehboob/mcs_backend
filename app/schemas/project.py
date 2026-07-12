"""Pydantic schemas for Project CRUD."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime


class ProjectCreate(BaseModel):
    """Request body for creating a new Project."""

    name: str
    default_provider: str = "gemini"
    default_model: str = "gemini-2.5-flash"
    custom_base_url: str | None = None
    token_limit: int | None = None
    persona: str | None = None
    instructions: str | None = None
    negative_constraints: str | None = None
    safety_settings: dict | None = None


class ProjectResponse(BaseModel):
    """Response model for a Project."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    default_provider: str
    default_model: str
    custom_base_url: str | None
    token_limit: int | None
    persona: str | None
    instructions: str | None
    negative_constraints: str | None
    safety_settings: dict | None


class ProjectUpdate(BaseModel):
    """Request body for updating a Project."""

    name: str | None = None
    default_provider: str | None = None
    default_model: str | None = None
    custom_base_url: str | None = None
    token_limit: int | None = None
    persona: str | None = None
    instructions: str | None = None
    negative_constraints: str | None = None
    safety_settings: dict | None = None
