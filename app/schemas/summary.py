"""Pydantic schemas for Summary Node endpoints."""

from pydantic import BaseModel


class SummaryGenerateRequest(BaseModel):
    """Request to generate a summary for a branch."""

    branch_id: int
    model: str = "gemini-2.5-flash"


class SummaryDraftResponse(BaseModel):
    """Response with a draft summary Node (not yet linked)."""

    draft_node_id: int | None
    name: str
    content: str
    branch_id: int
    pair_count: int


class SummaryReplaceRequest(BaseModel):
    """Request to apply (replace) a summary on a branch."""

    summary_node_id: int
    branch_id: int
    cutoff_position: int  # Index into the pair sequence (e.g., 6 means cutoff after pair 6)


class SummaryActionResponse(BaseModel):
    """Response after a summary action (replace/disconnect/delete)."""

    branch_id: int
    action: str
    linked_summary_node_id: int | None
    summary_cutoff_position: int | None
    token_count: int | None
