"""Graph API — Eagle View endpoint and GraphLayoutPosition CRUD.

Implements consolidated spec § (Eagle View Data) and M6-T1 acceptance criteria.

The graph endpoint returns all Pairs/Branches/Nodes for a project plus their
real edges: fork edges, sequence edges, and summary-cutoff edges.

GraphLayoutPosition is purely cosmetic — zero interaction with lineage or tokens.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import (
    Branch as BranchModel,
    GraphLayoutPosition as LayoutModel,
    Node as NodeModel,
    PRPair as PRPairModel,
)
from app.schemas.graph import (
    GraphEdge,
    GraphLayoutRequest,
    GraphLayoutResponse,
    GraphNode,
    GraphResponse,
)

router = APIRouter(prefix="/graph", tags=["graph"])


def _project_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/project/{project_id}", response_model=GraphResponse)
async def get_graph(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the full graph for a project: nodes, edges, and layout positions.

    Includes:
      - All branches, PRPairs, and Nodes as graph nodes
      - Fork edges (parent branch -> child branch)
      - Sequence edges (branch -> its PRPairs in order)
      - Summary-cutoff edges (summary node -> cutoff pair)
    """
    # Fetch all entities for the project
    branches_result = await db.execute(
        select(BranchModel).where(BranchModel.project_id == project_id)
    )
    branches = list(branches_result.scalars().all())

    if branches:
        pairs_result = await db.execute(
            select(PRPairModel).where(
                PRPairModel.branch_id.in_([b.id for b in branches])
            )
        )
        pairs = list(pairs_result.scalars().all())
    else:
        pairs = []

    nodes_result = await db.execute(
        select(NodeModel).where(NodeModel.project_id == project_id)
    )
    nodes = list(nodes_result.scalars().all())

    layouts_result = await db.execute(
        select(LayoutModel).where(LayoutModel.project_id == project_id)
    )
    layouts = list(layouts_result.scalars().all())

    # Build graph nodes
    graph_nodes: list[GraphNode] = []
    for b in branches:
        graph_nodes.append(GraphNode(
            id=b.id, type="branch", label=b.label,
        ))
    for p in pairs:
        graph_nodes.append(GraphNode(
            id=p.id, type="pair",
            prompt_text=p.prompt_text[:100] if p.prompt_text else None,
        ))
    for n in nodes:
        graph_nodes.append(GraphNode(
            id=n.id, type="node", name=n.name, content=n.content[:100] if n.content else None,
            node_type=n.type,
        ))

    # Build edges
    edges: list[GraphEdge] = []

    # Fork edges: parent branch -> child branch
    for b in branches:
        if b.parent_branch_id is not None:
            edges.append(GraphEdge(
                source_id=b.parent_branch_id,
                source_type="branch",
                target_id=b.id,
                target_type="branch",
                edge_type="fork",
            ))

    # Sequence edges: branch -> its pairs
    for p in pairs:
        edges.append(GraphEdge(
            source_id=p.branch_id,
            source_type="branch",
            target_id=p.id,
            target_type="pair",
            edge_type="sequence",
        ))

    # Summary-cutoff edges: branch with linked_summary_node_id -> summary
    for b in branches:
        if b.linked_summary_node_id is not None:
            edges.append(GraphEdge(
                source_id=b.linked_summary_node_id,
                source_type="node",
                target_id=b.id,
                target_type="branch",
                edge_type="summary_cutoff",
            ))

    return {
        "nodes": [gn.model_dump() for gn in graph_nodes],
        "edges": [ge.model_dump() for ge in edges],
        "layout_positions": layouts,
    }


# --- GraphLayoutPosition CRUD (purely cosmetic) ---

@router.post("/layout/project/{project_id}", response_model=GraphLayoutResponse, status_code=status.HTTP_201_CREATED)
async def create_layout(
    project_id: int,
    body: GraphLayoutRequest,
    db: AsyncSession = Depends(get_db),
) -> LayoutModel:
    """Create or update a layout position."""
    # Upsert: delete existing then create
    if body.branch_id:
        await db.execute(
            LayoutModel.__table__.delete().where(
                LayoutModel.project_id == project_id,
                LayoutModel.branch_id == body.branch_id,
            )
        )
    if body.node_id:
        await db.execute(
            LayoutModel.__table__.delete().where(
                LayoutModel.project_id == project_id,
                LayoutModel.node_id == body.node_id,
            )
        )

    layout = LayoutModel(
        project_id=project_id,
        branch_id=body.branch_id,
        node_id=body.node_id,
        x=body.x,
        y=body.y,
        z=body.z,
    )
    db.add(layout)
    await db.commit()
    await db.refresh(layout)
    return layout


@router.delete("/layout/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_layout(
    layout_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a layout position."""
    result = await db.execute(
        select(LayoutModel).where(LayoutModel.id == layout_id)
    )
    layout = result.scalar_one_or_none()
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layout not found")
    await db.delete(layout)
    await db.commit()
