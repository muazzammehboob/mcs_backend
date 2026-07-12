"""Attachment file storage logic.

Handles saving uploaded files to local disk under a project-scoped directory.
Zero framework imports — pure filesystem operations.
"""

from __future__ import annotations

import os
import pathlib
from uuid import uuid4


_ATTACHMENT_BASE_DIR = pathlib.Path("./data/attachments")


def ensure_storage() -> None:
    """Create the attachment storage directory if it doesn't exist."""
    _ATTACHMENT_BASE_DIR.mkdir(parents=True, exist_ok=True)


def store_file(project_id: int, filename: str, content: bytes) -> str:
    """Save file content to a project-scoped directory.

    Args:
        project_id: The project this file belongs to.
        filename: Original filename (used for extension only).
        content: Raw file bytes.

    Returns:
        Absolute path to the stored file.
    """
    ensure_storage()
    project_dir = _ATTACHMENT_BASE_DIR / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    ext = pathlib.Path(filename).suffix
    unique_name = f"{uuid4().hex}{ext}"
    file_path = project_dir / unique_name

    file_path.write_bytes(content)
    return str(file_path.absolute())


def delete_file(file_path: str) -> None:
    """Delete a stored file. Silently ignores missing files."""
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
