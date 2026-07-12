"""Tests for Project CRUD.

Acceptance criterion: POST /projects creates a Project row AND a Branch row
with parent_branch_id=NULL, parent_pr_pair_id=NULL, type='standard'.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Branch, Project


@pytest.mark.asyncio
async def test_create_project_and_root_branch(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /projects creates a Project and a Root Branch in one transaction."""
    # Monkey-patch the dependency to use our test session
    from app.api.projects import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    original_deps = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    try:
        response = await client.post(
            "/projects",
            json={"name": "Test Project", "default_model": "gemini-2.5-flash"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert "id" in data
        project_id = data["id"]

        # Verify the branch was created in the DB using the same session
        result = await db_session.execute(
            select(Branch).where(Branch.project_id == project_id)
        )
        branch = result.scalar_one_or_none()
        assert branch is not None
        assert branch.parent_branch_id is None
        assert branch.parent_pr_pair_id is None
        assert branch.type == "standard"
    finally:
        app.dependency_overrides = original_deps


@pytest.mark.asyncio
async def test_create_project_response_schema(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Response conforms to ProjectResponse schema."""
    from app.api.projects import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    original_deps = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    try:
        response = await client.post(
            "/projects",
            json={
                "name": "Schema Test",
                "default_provider": "gemini",
                "default_model": "gemini-2.5-flash",
                "persona": "Test persona",
                "token_limit": 8192,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["name"] == "Schema Test"
        assert data["default_provider"] == "gemini"
        assert data["default_model"] == "gemini-2.5-flash"
        assert data["persona"] == "Test persona"
        assert data["token_limit"] == 8192
        assert "created_at" in data
    finally:
        app.dependency_overrides = original_deps
