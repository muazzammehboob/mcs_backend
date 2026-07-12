"""Tests for Node API.

Implements M2-T1 acceptance criteria.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Node, Project
from app.api.projects import get_db as projects_get_db
from app.api.nodes import get_db as nodes_get_db
from app.main import app


async def _create_project(db: AsyncSession) -> int:
    """Helper: create a project and return its ID."""
    project = Project(name="Node Test", default_model="gemini-2.5-flash")
    db.add(project)
    await db.commit()
    return project.id


@pytest.mark.asyncio
async def test_create_node_duplicate_name_returns_409(client: AsyncClient, db_session: AsyncSession) -> None:
    """Creating a Node with a duplicate name in the same project returns 409.

    M2-T1 acceptance criterion:
    Creating a Node named identically (case-sensitive) to an existing Node
    in the same project returns 409.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[nodes_get_db] = override_db

    try:
        project_id = await _create_project(db_session)

        # Create first node
        response = await client.post(
            f"/nodes/project/{project_id}",
            json={"name": "MyNode", "content": "First content"},
        )
        assert response.status_code == 201

        # Try to create second node with same name
        response = await client.post(
            f"/nodes/project/{project_id}",
            json={"name": "MyNode", "content": "Second content"},
        )
        assert response.status_code == 409
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_node_cycle_detection(client: AsyncClient, db_session: AsyncSession) -> None:
    """Creating Node A that @mentions Node B, then editing B to @mention A, is rejected.

    M2-T1 acceptance criterion:
    Creating Node A that @mentions Node B, then editing Node B to @mention Node A,
    is rejected with 400 and does not save.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[nodes_get_db] = override_db

    try:
        project_id = await _create_project(db_session)

        # Create Node A that mentions Node B
        response = await client.post(
            f"/nodes/project/{project_id}",
            json={"name": "NodeA", "content": "See @{NodeB}"},
        )
        assert response.status_code == 201
        node_a = response.json()

        # Create Node B (no mention of A yet)
        response = await client.post(
            f"/nodes/project/{project_id}",
            json={"name": "NodeB", "content": "Initial content"},
        )
        assert response.status_code == 201
        node_b = response.json()

        # Now try to edit Node B to mention Node A — should be rejected
        response = await client.put(
            f"/nodes/{node_b['id']}",
            json={"content": "See @{NodeA}"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "cycle" in str(data)
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_node_crud_full(client: AsyncClient, db_session: AsyncSession) -> None:
    """Full CRUD: create, get, update, list, delete."""
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[nodes_get_db] = override_db

    try:
        project_id = await _create_project(db_session)

        # Create
        response = await client.post(
            f"/nodes/project/{project_id}",
            json={"name": "TestNode", "content": "Hello"},
        )
        assert response.status_code == 201
        node = response.json()
        assert node["name"] == "TestNode"

        # Get
        response = await client.get(f"/nodes/{node['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "TestNode"

        # Update
        response = await client.put(
            f"/nodes/{node['id']}",
            json={"content": "Updated content"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "Updated content"
        assert response.json()["version_counter"] == 1

        # List
        response = await client.get(f"/nodes/project/{project_id}")
        assert response.status_code == 200
        assert len(response.json()) == 1

        # Delete
        response = await client.delete(f"/nodes/{node['id']}")
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/nodes/{node['id']}")
        assert response.status_code == 404
    finally:
        app.dependency_overrides = {}
