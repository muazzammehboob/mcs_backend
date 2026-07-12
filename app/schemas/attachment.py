"""Pydantic schemas for Attachment endpoints."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime


class AttachmentUploadResponse(BaseModel):
    """Response after uploading an attachment."""

    attachment_id: int
    file_path: str
    mime_type: str
    original_filename: str
    size_bytes: int
    gemini_file_uri: str | None = None


class AttachmentResponse(BaseModel):
    """Response model for an Attachment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    pair_id: int
    file_path: str
    mime_type: str
    original_filename: str
    size_bytes: int
    created_at: datetime
