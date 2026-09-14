import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    storage_key: Mapped[str] = mapped_column(String(1024))
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="UPLOADED")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="chunks")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING, RUNNING, DONE, FAILED
    current_step: Mapped[str] = mapped_column(String(64), default="")  # ดู runner.py — ชื่อ step ปัจจุบันระหว่าง RUNNING
    llm_backend: Mapped[str] = mapped_column(String(32), default="openai")
    embed_model_name: Mapped[str] = mapped_column(String(128), default="BAAI/bge-m3")
    best_umap_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="runs")
    assignments: Mapped[list["ChunkClusterAssignment"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    clusters: Mapped[list["ClusterResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    umap_grid: Mapped[list["UmapGridResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ClusterResult(Base):
    __tablename__ = "cluster_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    cluster_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    centroid_x: Mapped[float] = mapped_column(Float, default=0.0)
    centroid_y: Mapped[float] = mapped_column(Float, default=0.0)

    run: Mapped["PipelineRun"] = relationship(back_populates="clusters")


class ChunkClusterAssignment(Base):
    __tablename__ = "chunk_cluster_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    cluster_id: Mapped[int] = mapped_column(Integer)  # >=0 cluster จริง, -1 noise (ไม่มี peak เลย), -2 bridge point
    bridge_between: Mapped[list | None] = mapped_column(JSON, nullable=True)

    run: Mapped["PipelineRun"] = relationship(back_populates="assignments")
    chunk: Mapped["Chunk"] = relationship()


class UmapGridResult(Base):
    __tablename__ = "umap_grid_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    n_neighbors: Mapped[int] = mapped_column(Integer)
    min_dist: Mapped[float] = mapped_column(Float)
    silhouette: Mapped[float] = mapped_column(Float)
    davies_bouldin: Mapped[float] = mapped_column(Float)
    entropy: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)

    run: Mapped["PipelineRun"] = relationship(back_populates="umap_grid")
