import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import qdrant_store
from app.config import settings
from app.db import get_db
from app.models import Project
from app.schemas import SearchHit, SearchResultsOut
from app.services.embedding import embed_texts

router = APIRouter(prefix="/api/projects/{project_id}/search", tags=["search"])


@router.get("", response_model=SearchResultsOut)
async def search_project(
    project_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search บน vector มิติสูงใน Qdrant — ไม่ใช้ 2D UMAP projection
    (ดูเหตุผลการแยก search/taxonomy ที่ docs/hierarchical-taxonomy-concept.md section 3)
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    query_vector = embed_texts([q], prompt=settings.embed_prompt)[0].tolist()
    hits = qdrant_store.search(project_id, query_vector, top_k=top_k)

    return SearchResultsOut(
        query=q,
        hits=[
            SearchHit(
                chunk_id=uuid.UUID(hit.payload["chunk_id"]),
                document_id=uuid.UUID(hit.payload["document_id"]),
                page_number=hit.payload.get("page_number"),
                text=hit.payload["text"],
                score=hit.score,
            )
            for hit in hits
        ],
    )
