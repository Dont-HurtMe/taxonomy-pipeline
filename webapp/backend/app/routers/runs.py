import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Chunk, Project
from app.schemas import ChunkAssignmentOut, ClusterResultOut, RunCreate, RunOut, RunResultsOut, UmapGridRowOut
from app.services import mlflow_client
from app.services.pipeline_client import PipelineUnavailableError, trigger_run

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["runs"])


def _epoch_ms_to_dt(ms: int | None) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None


def _map_status(run) -> str:
    """map mlflow native run status (RUNNING/SCHEDULED/FINISHED/FAILED/KILLED) + tag current_step
    (ที่ pipeline service เซ็ตละเอียดกว่า) กลับเป็น vocabulary เดิมที่ frontend รู้จัก: PENDING/RUNNING/
    DONE/FAILED (ดู frontend/src/public/css/style.css .badge-* — ต้องตรงเป๊ะ ไม่งั้น badge ไม่ขึ้นสี)
    """
    status = run.info.status
    if status == "FINISHED":
        return "DONE"
    if status in ("FAILED", "KILLED"):
        return "FAILED"
    if status == "SCHEDULED":
        return "PENDING"
    return "PENDING" if run.data.tags.get("current_step", "PENDING") == "PENDING" else "RUNNING"


def _to_run_out(run) -> RunOut:
    tags = run.data.tags
    params = run.data.params
    metrics = run.data.metrics
    status = _map_status(run)

    best_umap_params = None
    if "best_n_neighbors" in metrics:
        best_umap_params = {
            "n_neighbors": metrics["best_n_neighbors"],
            "min_dist": metrics["best_min_dist"],
            "score": metrics["best_score"],
        }

    return RunOut(
        id=run.info.run_id,
        status=status,
        current_step=tags.get("current_step", status),
        llm_backend=tags.get("llm_backend", params.get("llm_backend", "")),
        embed_model_name=params.get("embed_model_name", ""),
        best_umap_params=best_umap_params,
        error_message=tags.get("error_message"),
        created_at=_epoch_ms_to_dt(run.info.start_time) or datetime.now(timezone.utc),
        started_at=_epoch_ms_to_dt(run.info.start_time),
        finished_at=_epoch_ms_to_dt(run.info.end_time),
    )


@router.post("", response_model=RunOut, status_code=202)
async def create_run(project_id: uuid.UUID, payload: RunCreate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    try:
        run_id = await trigger_run(project_id, payload.llm_backend)
    except PipelineUnavailableError as e:
        raise HTTPException(status_code=502, detail=f"pipeline service ไม่ตอบสนอง: {e}") from e

    run = mlflow_client.get_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=502, detail="สร้าง run สำเร็จแต่ query กลับจาก mlflow ไม่พบ")
    return _to_run_out(run)


@router.get("", response_model=list[RunOut])
async def list_runs(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return [_to_run_out(r) for r in mlflow_client.list_runs(project_id)]


@router.get("/{run_id}", response_model=RunOut)
async def get_run(project_id: uuid.UUID, run_id: str):
    run = mlflow_client.get_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _to_run_out(run)


@router.get("/{run_id}/results", response_model=RunResultsOut)
async def get_run_results(project_id: uuid.UUID, run_id: str, db: AsyncSession = Depends(get_db)):
    run = mlflow_client.get_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    run_out = _to_run_out(run)
    if run_out.status != "DONE":
        raise HTTPException(status_code=409, detail=f"run status is {run_out.status}, not DONE yet")

    clusters_df = mlflow_client.download_artifact_df(project_id, run_id, "clusters.parquet")
    assignments_df = mlflow_client.download_artifact_df(project_id, run_id, "assignments.parquet")
    umap_grid_df = mlflow_client.download_artifact_df(project_id, run_id, "umap_grid.parquet")
    if clusters_df is None or assignments_df is None or umap_grid_df is None:
        raise HTTPException(status_code=502, detail="run สถานะ DONE แต่ยังหา artifact ผลลัพธ์จาก mlflow ไม่ครบ")

    clusters = [
        ClusterResultOut(
            cluster_id=int(row["cluster_id"]),
            name=str(row["name"]),
            size=int(row["size"]),
            centroid_x=float(row["centroid_x"]),
            centroid_y=float(row["centroid_y"]),
        )
        for row in clusters_df.to_dict("records")
    ]
    umap_grid = [
        UmapGridRowOut(
            n_neighbors=int(row["n_neighbors"]),
            min_dist=float(row["min_dist"]),
            silhouette=float(row["silhouette"]),
            davies_bouldin=float(row["davies_bouldin"]),
            entropy=float(row["entropy"]),
            score=float(row["score"]),
        )
        for row in umap_grid_df.to_dict("records")
    ]

    chunk_ids = [uuid.UUID(cid) for cid in assignments_df["chunk_id"]]
    chunks_result = await db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    chunk_by_id = {c.id: c for c in chunks_result.scalars().all()}

    assignments = []
    for row in assignments_df.to_dict("records"):
        chunk_id = uuid.UUID(row["chunk_id"])
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            continue  # chunk ต้นฉบับถูกลบไปแล้วหลัง run นี้ (เช่นลบ document) — ข้ามแทนพัง 500
        bridge_between = json.loads(row["bridge_between"]) if row["bridge_between"] else None
        assignments.append(
            ChunkAssignmentOut(
                chunk_id=chunk_id,
                text=chunk.text,
                document_id=chunk.document_id,
                page_number=chunk.page_number,
                x=float(row["x"]),
                y=float(row["y"]),
                cluster_id=int(row["cluster_id"]),
                bridge_between=bridge_between,
            )
        )

    return RunResultsOut(run=run_out, clusters=clusters, assignments=assignments, umap_grid=umap_grid)
