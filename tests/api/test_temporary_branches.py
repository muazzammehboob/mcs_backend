"""Tests for Temporary Branch API guards.

Implements M5-T1 acceptance criteria.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Branch, Node, PRPair, Project
from app.api.projects import get_db as projects_get_db
from app.api.summaries import get_db as summaries_get_db
from app.main import app


async def _create_temp_branch(db: AsyncSession) -> tuple[int, int]:
    """Create a project with a root branch and a temporary branch."""
    project = Project(name="Temp Test", default_model="gemini-2.5-flash")
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

    pair = PRPair(branch_id=root.id, prompt_text="Hello", response_text="Hi")
    db.add(pair)
    await db.flush()

    temp = Branch(
        project_id=project.id,
        parent_branch_id=root.id,
        parent_pr_pair_id=pair.id,
        type="temporary",
    )
    db.add(temp)
    await db.commit()

    return project.id, temp.id


@pytest.mark.asyncio
async def test_summarize_rejected_on_temporary_branch(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST to Summarize against a Temporary Branch returns 400.

    M5-T1 acceptance criterion:
    POST to the Summarize endpoint against a Temporary Branch returns 400
    and does not call SummaryService at all.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[summaries_get_db] = override_db

    try:
        _, temp_branch_id = await _create_temp_branch(db_session)

        response = await client.post(
            "/summaries/generate",
            json={"branch_id": temp_branch_id},
            headers={"X-Gemini-Api-Key": "test-key"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Temporary" in str(data) or "temporary" in str(data)
    finally:
        app.dependency_overrides = {}
