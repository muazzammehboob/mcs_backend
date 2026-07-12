"""Pydantic schemas for Node CRUD."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime


class NodeCreate(BaseModel):
    """Request body for creating a Node."""

    name: str
    content: str
    type: str = "manual"


class NodeUpdate(BaseModel):
    """Request body for updating a Node."""

    name: str | None = None
    content: str | None = None


class NodeResponse(BaseModel):
    """Response model for a Node."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    content: str
    type: str
    version_counter: int
    created_at: datetime


class NodeReferenceError(BaseModel):
    """Response model for @mention cycle detection error."""

    detail: str
    cycle: list[str]
