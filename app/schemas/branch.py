"""Pydantic schemas for Branch CRUD."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime


class BranchResponse(BaseModel):
    """Response model for a Branch."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    parent_branch_id: int | None
    parent_pr_pair_id: int | None
    type: str
    label: str | None
    cached_static_token_count: int | None
    linked_summary_node_id: int | None
    summary_cutoff_position: int | None
    created_at: datetime


class BranchForkRequest(BaseModel):
    """Request to fork a new branch from a completed PRPair."""

    pr_pair_id: int
    label: str | None = None


class BranchForkResponse(BaseModel):
    """Response after forking a branch."""

    branch: BranchResponse


class BranchUpdateRequest(BaseModel):
    """Request to update/rename a branch."""

    label: str | None = None


class BranchCountsResponse(BaseModel):
    """Response for branch-count-per-pair endpoint."""

    counts: dict[str, int]  # pr_pair_id str -> count


class MoveToParentPairResponse(BaseModel):
    """Response for 'move to parent pair' lookup."""

    parent_pr_pair_id: int | None


from app.schemas.pair import PRPairResponse

class LineageResponse(BaseModel):
    pairs: list[PRPairResponse]
    linked_summary_node_id: int | None = None
    summary_cutoff_position: int | None = None
    cached_static_token_count: int | None = None

