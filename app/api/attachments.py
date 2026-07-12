"""Attachment upload endpoint.

Implements consolidated spec §13: separate upload before LLM call.
Returns an attachment_id that can be referenced in subsequent send requests.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import Attachment as AttachmentModel
from app.schemas.attachment import AttachmentUploadResponse
from app.domain.attachments import store_file
from app.providers.gemini_files import GeminiFileUploader
from app.providers.exceptions import GeminiAPIError
from app.deps import get_gemini_api_key

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/project/{project_id}", response_model=AttachmentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    project_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_gemini_api_key),
) -> dict:
    """Upload a file and return an attachment_id.

    The file is stored locally and optionally uploaded to Gemini File API
    for later reference in chat completions.

    Args:
        project_id: The project to associate the attachment with.
        file: The uploaded file.

    Returns:
        Attachment metadata including attachment_id and gemini_file_uri.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename")

    content = await file.read()
    size_bytes = len(content)
    mime_type = file.content_type or "application/octet-stream"

    # Store locally
    file_path = store_file(project_id, file.filename, content)

    # Upload to Gemini File API
    uploader = GeminiFileUploader(api_key=api_key)
    gemini_uri: str | None = None
    try:
        gemini_uri = await uploader.upload_file(file_path, mime_type)
    except GeminiAPIError as exc:
        # Propagate Gemini errors as-is
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "gemini_upload_failed", "message": exc.message},
        ) from exc
    finally:
        await uploader.close()

    # Persist metadata (pair_id=0 placeholder, updated when linked to a Pair)
    attachment = AttachmentModel(
        project_id=project_id,
        pair_id=None,  # Will be set when the attachment is linked to a PRPair
        file_path=file_path,
        mime_type=mime_type,
        original_filename=file.filename,
        size_bytes=size_bytes,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return {
        "attachment_id": attachment.id,
        "file_path": file_path,
        "mime_type": mime_type,
        "original_filename": file.filename,
        "size_bytes": size_bytes,
        "gemini_file_uri": gemini_uri,
    }
