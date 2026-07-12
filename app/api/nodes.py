"""Node CRUD API with @mention cycle detection.

Implements consolidated spec §9 (Nodes) and M2-T1 acceptance criteria.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.db.models import Node as NodeModel
from app.schemas.node import NodeCreate, NodeUpdate, NodeResponse
from app.domain.nodes import detect_cycle

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _node_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")


def _name_conflict(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Node named '{name}' already exists in this project",
    )


def _cycle_detected(cycle: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"message": "@mention cycle detected", "cycle": cycle},
    )


@router.post("/project/{project_id}", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    project_id: int,
    body: NodeCreate,
    db: AsyncSession = Depends(get_db),
) -> NodeModel:
    """Create a new Node in a project.

    Enforces per-project name uniqueness at the DB level.
    Rejects if @mention cycle would be created.
    """
    # Check for @mention cycles
    existing_nodes_result = await db.execute(
        select(NodeModel).where(NodeModel.project_id == project_id)
    )
    existing_nodes = existing_nodes_result.scalars().all()
    node_map = {n.name: n.content for n in existing_nodes}

    cycle = detect_cycle(body.name, body.content, node_map)
    if cycle is not None:
        raise _cycle_detected(cycle)

    node = NodeModel(
        project_id=project_id,
        name=body.name,
        content=body.content,
        type=body.type,
    )
    db.add(node)
    try:
        await db.commit()
        await db.refresh(node)
    except IntegrityError as exc:
        await db.rollback()
        if "UNIQUE constraint failed" in str(exc) and "nodes.project_id" in str(exc):
            raise _name_conflict(body.name) from None
        raise
    return node


@router.put("/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: int,
    body: NodeUpdate,
    db: AsyncSession = Depends(get_db),
) -> NodeModel:
    """Update a Node. Rejects if @mention cycle would be created."""
    result = await db.execute(
        select(NodeModel).where(NodeModel.id == node_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise _node_not_found()

    new_name = body.name if body.name is not None else node.name
    new_content = body.content if body.content is not None else node.content

    # Check for @mention cycles (exclude self from existing nodes)
    existing_nodes_result = await db.execute(
        select(NodeModel).where(
            NodeModel.project_id == node.project_id,
            NodeModel.id != node_id,
        )
    )
    existing_nodes = existing_nodes_result.scalars().all()
    node_map = {n.name: n.content for n in existing_nodes}

    cycle = detect_cycle(new_name, new_content, node_map)
    if cycle is not None:
        raise _cycle_detected(cycle)

    node.name = new_name
    node.content = new_content
    node.version_counter += 1

    try:
        await db.commit()
        await db.refresh(node)
    except IntegrityError as exc:
        await db.rollback()
        if "UNIQUE constraint failed" in str(exc) and "nodes.project_id" in str(exc):
            raise _name_conflict(new_name) from None
        raise
    return node


@router.get("/project/{project_id}", response_model=list[NodeResponse])
async def list_nodes(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[NodeModel]:
    """List all nodes in a project."""
    result = await db.execute(
        select(NodeModel).where(NodeModel.project_id == project_id)
    )
    return list(result.scalars().all())


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
) -> NodeModel:
    """Get a single Node by ID."""
    result = await db.execute(
        select(NodeModel).where(NodeModel.id == node_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise _node_not_found()
    return node


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a Node by ID."""
    result = await db.execute(
        select(NodeModel).where(NodeModel.id == node_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise _node_not_found()
    await db.delete(node)
    await db.commit()
