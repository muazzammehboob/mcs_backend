"""Pydantic models for lineage assembly.

Pure dataclasses used by LineageAssembler and TokenEstimator.
Zero SQLAlchemy/FastAPI imports in the domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LineagePair:
    """A simplified PRPair for lineage assembly.

    Consolidated spec §4.5: lineage includes both prompt and response turns.
    """

    id: int
    branch_id: int
    prompt_text: str
    response_text: str
    generation_params: dict | None = None
    created_at: datetime | None = None


@dataclass
class LineageBranch:
    """A simplified Branch for lineage assembly."""

    id: int
    project_id: int
    parent_branch_id: int | None = None
    parent_pr_pair_id: int | None = None
    type: str = "standard"
    label: str | None = None
    cached_static_token_count: int | None = None
    linked_summary_node_id: int | None = None
    summary_cutoff_position: int | None = None
    created_at: datetime | None = None


@dataclass
class LineageNode:
    """A simplified Node for @mention resolution (placeholder for M2)."""

    id: int
    project_id: int
    name: str
    content: str
    type: str = "manual"


@dataclass
class AssembledLineage:
    """Result of lineage assembly."""

    pairs: list[LineagePair] = field(default_factory=list)
