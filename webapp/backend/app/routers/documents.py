import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import Chunk, Document, Project
from app.schemas import DocumentOut
from app.services.chunking import chunk_pages
from app.services.pdf_utils import extract_pages
from app.storage import upload_bytes

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentOut)
async def upload_document(project_id: uuid.UUID, file: UploadFile, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    data = await file.read()
    content_type = file.content_type or ""
    storage_key = upload_bytes(data, file.filename or "upload", content_type)

    document = Document(
        project_id=project_id,
        original_filename=file.filename or "upload",
        content_type=content_type,
        storage_key=storage_key,
        status="UPLOADED",
    )
    db.add(document)
    await db.flush()

    try:
        pages = extract_pages(data, content_type)
        document.page_count = len(pages)
        pairs = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
        for idx, (text, page_number) in enumerate(pairs):
            db.add(Chunk(document_id=document.id, project_id=project_id, chunk_index=idx, page_number=page_number, text=text))
        document.status = "CHUNKED"
    except Exception as e:  # noqa: BLE001 — เก็บ error ไว้ให้ผู้ใช้เห็นสถานะเอกสารนี้ ไม่ทำให้ request 500
        document.status = "FAILED"
        document.error_message = str(e)

    await db.commit()
    await db.refresh(document)

    chunk_count = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id))
    out = DocumentOut.model_validate(document)
    out.chunk_count = chunk_count or 0
    return out


@router.get("", response_model=list[DocumentOut])
async def list_documents(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.project_id == project_id).order_by(Document.uploaded_at.desc()))
    documents = list(result.scalars().all())
    out = []
    for doc in documents:
        count = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id))
        item = DocumentOut.model_validate(doc)
        item.chunk_count = count or 0
        out.append(item)
    return out
