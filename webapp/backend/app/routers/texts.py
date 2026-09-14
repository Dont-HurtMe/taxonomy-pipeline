import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import Chunk, Document, Project
from app.schemas import DocumentOut, TextsIn
from app.services.chunking import chunk_pages
from app.storage import upload_bytes

router = APIRouter(prefix="/api/projects/{project_id}/texts", tags=["texts"])


@router.post("", response_model=DocumentOut)
async def import_texts(project_id: uuid.UUID, payload: TextsIn, db: AsyncSession = Depends(get_db)):
    """รับ list[str] ตรง ๆ (เช่นจาก `texts = df["content"].dropna().astype(str).tolist()`) — ไม่ผ่าน PDF/MinIO
    เก็บ raw list ลง MinIO เป็น JSON เพื่อ trace ย้อนกลับได้เหมือน document อื่น ๆ แล้ว chunk ต่อด้วย
    path เดียวกับเอกสาร (ทำให้ pipeline ด้านหลังไม่ต้องรู้ว่า input มาจากไฟล์หรือ script)
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if not payload.texts:
        raise HTTPException(status_code=400, detail="texts ว่าง")

    raw = json.dumps(payload.texts, ensure_ascii=False).encode("utf-8")
    filename = payload.source_name or f"texts-import-{datetime.now(timezone.utc):%Y%m%d%H%M%S}.json"
    storage_key = upload_bytes(raw, filename, "application/json")

    document = Document(
        project_id=project_id,
        original_filename=filename,
        content_type="application/json",
        storage_key=storage_key,
        page_count=len(payload.texts),
        status="UPLOADED",
    )
    db.add(document)
    await db.flush()

    try:
        pairs = chunk_pages(payload.texts, settings.chunk_size, settings.chunk_overlap)
        for idx, (text, page_number) in enumerate(pairs):
            db.add(Chunk(document_id=document.id, project_id=project_id, chunk_index=idx, page_number=page_number, text=text))
        document.status = "CHUNKED"
    except Exception as e:  # noqa: BLE001 — เก็บ error ไว้ให้เห็นสถานะ import นี้ ไม่ทำให้ request 500
        document.status = "FAILED"
        document.error_message = str(e)

    await db.commit()
    await db.refresh(document)

    chunk_count = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id))
    out = DocumentOut.model_validate(document)
    out.chunk_count = chunk_count or 0
    return out
