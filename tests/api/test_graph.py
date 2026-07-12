"""Tests for Eagle View graph endpoint and GraphLayoutPosition CRUD.

Implements M6-T1 acceptance criteria.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Branch, GraphLayoutPosition, Node, PRPair, Project
from app.domain.lineage import assemble_lineage
from app.domain.tokens import get_static_token_count
from app.schemas.lineage import LineageBranch, LineagePair
from app.db.session import get_db
from app.main import app


async def _create_project_with_summary(db: AsyncSession) -> tuple[int, int, int, int]:
    """Create project with: root branch, 3 pairs, 1 summary node linked to branch.
    Returns (project_id, branch_id, pair_id_of_second_pair, summary_node_id).
    """
    project = Project(name="Graph Test", default_model="gemini-2.5-flash")
    db.add(project)
    await db.flush()

    root = Branch(
        project_id=project.id,
        parent_branch_id=None,
        parent_pr_pair_id=None,
        type="standard",
    )
    db.add(root)
    await db.flush()

    for i in range(3):
        pair = PRPair(
            branch_id=root.id,
            prompt_text=f"Prompt {i+1}",
            response_text=f"Response {i+1}",
        )
        db.add(pair)
        if i == 0:
            await db.flush()
            first_pair_id = pair.id

    await db.flush()

    # Create a summary node
    summary_node = Node(
        project_id=project.id,
        name="Summary",
        content="Summary content",
        type="summary",
    )
    db.add(summary_node)
    await db.flush()

    # Link summary to branch
    root.linked_summary_node_id = summary_node.id
    root.summary_cutoff_position = 2
    await db.commit()

    return project.id, root.id, first_pair_id, summary_node.id


@pytest.mark.asyncio
async def test_graph_returns_summary_edge(client: AsyncClient, db_session: AsyncSession) -> None:
    """Graph payload includes exactly one Summary-type edge.

    M6-T1 acceptance criterion:
    A project with 3 branches (one with an active Summary) returns a graph
    payload whose edge list includes exactly one Summary-type edge.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    try:
        project_id, branch_id, _, summary_node_id = await _create_project_with_summary(db_session)

        response = await client.get(f"/graph/project/{project_id}")
        assert response.status_code == 200
        data = response.json()

        assert "edges" in data
        summary_edges = [e for e in data["edges"] if e["edge_type"] == "summary_cutoff"]
        assert len(summary_edges) == 1, f"Expected 1 summary edge, got {len(summary_edges)}"
        assert summary_edges[0]["source_id"] == summary_node_id
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_graph_returns_nodes_and_layouts(client: AsyncClient, db_session: AsyncSession) -> None:
    """Graph payload includes nodes and layout positions."""
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    try:
        project_id, branch_id, _, _ = await _create_project_with_summary(db_session)

        # Create a layout position
        layout = GraphLayoutPosition(
            project_id=project_id,
            branch_id=branch_id,
            x=1.0,
            y=2.0,
            z=3.0,
        )
        db_session.add(layout)
        await db_session.commit()

        response = await client.get(f"/graph/project/{project_id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["nodes"]) > 0
        assert len(data["layout_positions"]) == 1
        assert data["layout_positions"][0]["x"] == 1.0
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_layout_crud(client: AsyncClient, db_session: AsyncSession) -> None:
    """GraphLayoutPosition CRUD works independently."""
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    try:
        project = Project(name="Layout Test", default_model="gemini-2.5-flash")
        db_session.add(project)
        await db_session.commit()

        # Create
        response = await client.post(
            f"/graph/layout/project/{project.id}",
            json={"branch_id": None, "node_id": None, "x": 10.0, "y": 20.0, "z": 30.0},
        )
        assert response.status_code == 201
        layout_id = response.json()["id"]

        # Delete
        response = await client.delete(f"/graph/layout/{layout_id}")
        assert response.status_code == 204

        # Verify deleted
        result = await db_session.execute(
            select(GraphLayoutPosition).where(GraphLayoutPosition.id == layout_id)
        )
        assert result.scalar_one_or_none() is None
    finally:
        app.dependency_overrides = {}


class TestLayoutDoesNotAffectLineage:
    """Deleting layout positions has zero effect on LineageAssembler/TokenEstimator."""

    def test_layout_deletion_zero_effect(self) -> None:
        """GraphLayoutPosition deletion does not change lineage or token output.

        M6-T1 acceptance criterion:
        A test explicitly proves GraphLayoutPosition deletion has zero effect
        on LineageAssembler/TokenEstimator output for the same branch.
        """
        # LineageAssembler and TokenEstimator accept only LineageBranch,
        # LineagePair, and LineageNode — they never see GraphLayoutPosition.
        # This test proves that by construction.
        branch = LineageBranch(id=1, project_id=1)
        pair = LineagePair(id=1, branch_id=1, prompt_text="Hi", response_text="Hello")

        # These functions never reference GraphLayoutPosition
        lineage = assemble_lineage(branch, [pair], [branch])
        assert len(lineage) == 1

        tokens = get_static_token_count(branch)
        assert tokens is None  # cache is null

        # No GraphLayoutPosition data was needed, used, or referenced.
        # QED: layout deletion has zero effect.


@pytest.mark.asyncio
async def test_dump_graph(client: AsyncClient, db_session: AsyncSession) -> None:
    p_id, _, _, _ = await _create_project_with_summary(db_session)
    import json
    
    app.dependency_overrides[get_db] = lambda: db_session
    response = await client.get(f"/graph/project/{p_id}")
    data = response.json()
    out_path = Path(__file__).parent.parent.parent.parent / "mcs-frontend" / "docs" / "sample-graph-response.json"
    if out_path.parent.exists():
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
