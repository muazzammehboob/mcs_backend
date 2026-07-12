"""Pydantic schemas for PRPair."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime


class PRPairResponse(BaseModel):
    """Response model for a PRPair."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    prompt_text: str
    response_text: str
    generation_params: dict | None
    created_at: datetime
