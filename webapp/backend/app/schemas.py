import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    page_count: int | None
    status: str
    error_message: str | None
    uploaded_at: datetime
    chunk_count: int = 0

    model_config = {"from_attributes": True}


class TextsIn(BaseModel):
    """usecase: ส่ง list[str] เข้าระบบตรง ๆ จาก script (เช่น pandas อ่าน CSV) แทนอัปโหลดไฟล์
    ผ่าน chunking path เดียวกับเอกสาร — page_number ที่ได้ = index ใน `texts` (ไม่ใช่เลขหน้า PDF จริง)
    """

    texts: list[str]
    source_name: str = ""


class RunCreate(BaseModel):
    llm_backend: str | None = None  # None -> ใช้ default จาก settings


class RunOut(BaseModel):
    id: uuid.UUID
    status: str
    current_step: str
    llm_backend: str
    embed_model_name: str
    best_umap_params: dict | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ClusterResultOut(BaseModel):
    cluster_id: int
    name: str
    size: int
    centroid_x: float
    centroid_y: float

    model_config = {"from_attributes": True}


class ChunkAssignmentOut(BaseModel):
    chunk_id: uuid.UUID
    text: str
    document_id: uuid.UUID
    page_number: int | None
    x: float
    y: float
    cluster_id: int
    bridge_between: list[int] | None


class UmapGridRowOut(BaseModel):
    n_neighbors: int
    min_dist: float
    silhouette: float
    davies_bouldin: float
    entropy: float
    score: float

    model_config = {"from_attributes": True}


class RunResultsOut(BaseModel):
    run: RunOut
    clusters: list[ClusterResultOut]
    assignments: list[ChunkAssignmentOut]
    umap_grid: list[UmapGridRowOut]


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int | None
    text: str
    score: float


class SearchResultsOut(BaseModel):
    query: str
    hits: list[SearchHit]
