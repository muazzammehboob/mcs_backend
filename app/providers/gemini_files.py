"""Gemini File API adapter.

Implements consolidated spec §13: upload once, reference by URI.
Uses hand-rolled httpx calls (no google-genai SDK).

File API expiry: Gemini uploaded files expire after 48 hours server-side.
This is a known limitation documented here — no auto-refresh/re-upload logic.
"""

from __future__ import annotations

import logging

import httpx

from app.providers.exceptions import GeminiAPIError

logger = logging.getLogger(__name__)

_GEMINI_FILES_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiFileUploader:
    """Uploads files to Gemini's File API and returns a URI for referencing."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=_GEMINI_FILES_URL,
            headers={"x-goog-api-key": api_key},
            timeout=httpx.Timeout(120.0),
        )

    async def upload_file(self, file_path: str, mime_type: str) -> str:
        """Upload a file to Gemini File API and return its URI.

        Args:
            file_path: Local path to the file.
            mime_type: MIME type of the file.

        Returns:
            The Gemini file URI (e.g., "files/abc-123").

        Raises:
            GeminiAPIError: If the upload fails.
        """
        import pathlib

        path = pathlib.Path(file_path)
        if not path.exists():
            raise GeminiAPIError(f"File not found: {file_path}")

        file_bytes = path.read_bytes()
        num_bytes = len(file_bytes)

        # Step 1: Initial request to get upload URL
        metadata = {
            "file": {
                "display_name": path.name,
                "mime_type": mime_type,
            }
        }

        url = "/upload/v1beta/files"

        try:
            response = await self._client.post(
                url,
                data={"metadata": str(metadata).replace("'", '"')},
                files={"file": (path.name, file_bytes, mime_type)},
            )
        except httpx.HTTPError as exc:
            raise GeminiAPIError(f"Network error uploading file: {exc}") from exc

        if response.status_code >= 400:
            try:
                data = response.json()
                error_info = data.get("error", {})
                message = error_info.get("message", response.text)
            except Exception:
                message = response.text
            raise GeminiAPIError(
                message=message,
                status_code=response.status_code,
            )

        data = response.json()
        file_uri = data.get("file", {}).get("uri", "")
        if not file_uri:
            raise GeminiAPIError("No file URI in Gemini upload response")

        return file_uri

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
