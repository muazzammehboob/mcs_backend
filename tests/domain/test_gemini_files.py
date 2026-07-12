"""Tests for GeminiFileUploader.

Uses respx to mock HTTP calls. Implements M3-T2 acceptance criteria.
"""

import pytest
import respx
from httpx import Response

from app.providers.gemini_files import GeminiFileUploader
from app.providers.exceptions import GeminiAPIError


class TestUploadFile:
    """Tests for upload_file()."""

    @respx.mock
    async def test_uploads_file_and_returns_uri(self) -> None:
        """Upload returns a Gemini file URI on success."""
        url = "https://generativelanguage.googleapis.com/v1beta/upload/v1beta/files"
        respx.post(url).mock(return_value=Response(200, json={
            "file": {"uri": "files/test-file-123", "name": "files/test-file-123"}
        }))

        uploader = GeminiFileUploader(api_key="test-key")
        # Create a temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Hello World")
            temp_path = f.name

        try:
            uri = await uploader.upload_file(temp_path, "text/plain")
            assert uri == "files/test-file-123"
        finally:
            await uploader.close()
            import os
            os.remove(temp_path)

    @respx.mock
    async def test_gemini_error_propagates(self) -> None:
        """A Gemini error surfaces its actual error message to the caller.

        M3-T2 acceptance criterion:
        An oversized-file rejection from the Gemini File API surfaces its
        actual error message to the caller.
        """
        url = "https://generativelanguage.googleapis.com/v1beta/upload/v1beta/files"
        respx.post(url).mock(return_value=Response(413, json={
            "error": {"code": 413, "message": "File too large: exceeds 2GB limit", "status": "PAYLOAD_TOO_LARGE"}
        }))

        uploader = GeminiFileUploader(api_key="test-key")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"x")
            temp_path = f.name

        try:
            with pytest.raises(GeminiAPIError) as exc_info:
                await uploader.upload_file(temp_path, "application/octet-stream")
            assert "too large" in exc_info.value.message.lower() or "File too large" in exc_info.value.message
        finally:
            await uploader.close()
            import os
            os.remove(temp_path)
