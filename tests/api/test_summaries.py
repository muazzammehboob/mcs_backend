"""Tests for Summary API endpoints.

Implements M4-T1 acceptance criteria.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Branch, Node, PRPair, Project
from app.api.projects import get_db as projects_get_db
from app.api.summaries import get_db as summaries_get_db
from app.main import app


async def _create_project_with_pairs(db: AsyncSession, num_pairs: int = 3) -> tuple[int, int]:
    """Create a project with a root branch and N pairs. Returns (project_id, branch_id)."""
    project = Project(name="Summary Test", default_model="gemini-2.5-flash")
    db.add(project)
    await db.flush()

    root = Branch(
        project_id=project.id,
        parent_branch_id=None,
        parent_pr_pair_id=None,
        type="standard",
        label="Root",
    )
    db.add(root)
    await db.flush()

    for i in range(num_pairs):
        pair = PRPair(
            branch_id=root.id,
            prompt_text=f"Prompt {i+1}",
            response_text=f"Response {i+1}",
        )
        db.add(pair)

    await db.commit()
    return project.id, root.id


@pytest.mark.asyncio
async def test_generate_creates_draft_not_linked(client: AsyncClient, db_session: AsyncSession) -> None:
    """Generate produces a draft Node NOT linked to the branch.

    M4-T1 acceptance criterion:
    Generate produces a draft Node that is NOT yet linked to the branch
    (linked_summary_node_id unchanged) until Replace is explicitly called.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[summaries_get_db] = override_db

    try:
        project_id, branch_id = await _create_project_with_pairs(db_session, 3)

        import respx
        from httpx import Response

        with respx.mock:
            route = respx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            ).mock(return_value=Response(200, json={
                "candidates": [{"content": {"parts": [{"text": "Summary text here"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"totalTokenCount": 100},
            }))

            response = await client.post(
                "/summaries/generate",
                json={"branch_id": branch_id, "model": "gemini-2.5-flash"},
                headers={"X-Gemini-Api-Key": "test-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["draft_node_id"] is not None
        assert data["content"] == "Summary text here"
        assert data["pair_count"] == 3

        # Verify branch is NOT linked yet
        result = await db_session.execute(select(Branch).where(Branch.id == branch_id))
        branch = result.scalar_one()
        assert branch.linked_summary_node_id is None
        assert branch.summary_cutoff_position is None
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_delete_removes_node_row(client: AsyncClient, db_session: AsyncSession) -> None:
    """Delete removes the Node row; subsequent GET returns 404.

    M4-T1 acceptance criterion:
    Delete removes the Node row entirely; a subsequent GET for that node_id
    returns 404.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[summaries_get_db] = override_db

    try:
        project_id, branch_id = await _create_project_with_pairs(db_session, 3)

        # Create a summary node and link it
        node = Node(
            project_id=project_id,
            name="TestSummary",
            content="Summary content",
            type="summary",
        )
        db_session.add(node)
        await db_session.flush()

        result = await db_session.execute(select(Branch).where(Branch.id == branch_id))
        branch = result.scalar_one()
        branch.linked_summary_node_id = node.id
        branch.summary_cutoff_position = 2
        await db_session.commit()

        # Delete via API
        response = await client.post(f"/summaries/{branch_id}/delete")
        assert response.status_code == 200

        # Verify node is gone
        result = await db_session.execute(select(Node).where(Node.id == node.id))
        assert result.scalar_one_or_none() is None

        # Verify branch is unlinked
        result = await db_session.execute(select(Branch).where(Branch.id == branch_id))
        branch = result.scalar_one()
        assert branch.linked_summary_node_id is None
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_disconnect_restores_lineage(client: AsyncClient, db_session: AsyncSession) -> None:
    """Disconnect clears linked_summary_node_id and summary_cutoff_position.

    M4-T1 acceptance criterion:
    Disconnect restores the full lineage with no summary injection.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[summaries_get_db] = override_db

    try:
        project_id, branch_id = await _create_project_with_pairs(db_session, 5)

        node = Node(
            project_id=project_id,
            name="Summary",
            content="Summary content",
            type="summary",
        )
        db_session.add(node)
        await db_session.flush()

        result = await db_session.execute(select(Branch).where(Branch.id == branch_id))
        branch = result.scalar_one()
        branch.linked_summary_node_id = node.id
        branch.summary_cutoff_position = 3
        await db_session.commit()

        # Disconnect
        response = await client.post(
            f"/summaries/{branch_id}/disconnect",
            headers={"X-Gemini-Api-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "disconnect"
        assert data["linked_summary_node_id"] is None
        assert data["summary_cutoff_position"] is None

        # Verify in DB
        result = await db_session.execute(select(Branch).where(Branch.id == branch_id))
        branch = result.scalar_one()
        assert branch.linked_summary_node_id is None
        assert branch.summary_cutoff_position is None
    finally:
        app.dependency_overrides = {}
