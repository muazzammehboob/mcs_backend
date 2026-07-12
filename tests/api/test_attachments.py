"""Tests for Attachment upload endpoint.

Implements M3-T2 acceptance criteria.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project
from app.api.projects import get_db as projects_get_db
from app.api.attachments import get_db as attachments_get_db
from app.main import app


async def _create_project(db: AsyncSession) -> int:
    project = Project(name="Attachment Test", default_model="gemini-2.5-flash")
    db.add(project)
    await db.commit()
    return project.id


@pytest.mark.asyncio
async def test_upload_attachment_returns_id(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /attachments returns an attachment_id and persists metadata.

    M3-T2 acceptance criterion:
    POST /attachments with a valid file returns an attachment_id and persists
    file_path/mime_type/original_filename/size_bytes.
    """
    async def override_db():
        yield db_session

    app.dependency_overrides[projects_get_db] = override_db
    app.dependency_overrides[attachments_get_db] = override_db

    try:
        project_id = await _create_project(db_session)

        # We need to mock the Gemini upload since we don't have a real API key
        import respx
        from httpx import Response

        url = "https://generativelanguage.googleapis.com/v1beta/upload/v1beta/files"
        with respx.mock:
            respx.post(url).mock(return_value=Response(200, json={
                "file": {"uri": "files/test-123", "name": "files/test-123"}
            }))

            response = await client.post(
                f"/attachments/project/{project_id}",
                data={},
                files={"file": ("test.txt", b"Hello World", "text/plain")},
                headers={"X-Gemini-Api-Key": "test-key"},
            )

        assert response.status_code == 201
        data = response.json()
        assert "attachment_id" in data
        assert data["original_filename"] == "test.txt"
        assert data["mime_type"] == "text/plain"
        assert data["size_bytes"] == 11
        assert data["gemini_file_uri"] == "files/test-123"
    finally:
        app.dependency_overrides = {}
