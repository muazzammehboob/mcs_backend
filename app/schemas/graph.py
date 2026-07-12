"""Pydantic schemas for Eagle View graph endpoint."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime


class GraphNode(BaseModel):
    """A node in the graph (Branch, PRPair, or Node entity)."""

    id: int
    type: str  # "branch", "pair", "node"
    label: str | None = None
    name: str | None = None
    prompt_text: str | None = None
    content: str | None = None
    node_type: str | None = None  # for nodes: "manual" or "summary"


class GraphEdge(BaseModel):
    """An edge in the graph."""

    source_id: int
    source_type: str
    target_id: int
    target_type: str
    edge_type: str  # "fork", "sequence", "summary_cutoff", "contains"


class GraphLayoutRequest(BaseModel):
    """Request to update a layout position."""

    branch_id: int | None = None
    node_id: int | None = None
    x: float
    y: float
    z: float | None = None


class GraphLayoutResponse(BaseModel):
    """Response for a layout position."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    branch_id: int | None
    node_id: int | None
    x: float
    y: float
    z: float | None
    created_at: datetime


class GraphResponse(BaseModel):
    """Full graph payload for Eagle View."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    layout_positions: list[GraphLayoutResponse]
