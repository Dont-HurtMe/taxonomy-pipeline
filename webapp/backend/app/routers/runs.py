import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_db
from app.models import ChunkClusterAssignment, ClusterResult, PipelineRun, Project, UmapGridResult
from app.schemas import ChunkAssignmentOut, ClusterResultOut, RunCreate, RunOut, RunResultsOut, UmapGridRowOut
from app.services.runner import start_run

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["runs"])


@router.post("", response_model=RunOut)
async def create_run(project_id: uuid.UUID, payload: RunCreate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    run = PipelineRun(
        project_id=project_id,
        llm_backend=payload.llm_backend or settings.llm_backend,
        embed_model_name=settings.embed_model_name,
        status="PENDING",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    start_run(run.id)
    return run


@router.get("", response_model=list[RunOut])
async def list_runs(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineRun).where(PipelineRun.project_id == project_id).order_by(PipelineRun.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=RunOut)
async def get_run(project_id: uuid.UUID, run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(PipelineRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/results", response_model=RunResultsOut)
async def get_run_results(project_id: uuid.UUID, run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(PipelineRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "DONE":
        raise HTTPException(status_code=409, detail=f"run status is {run.status}, not DONE yet")

    clusters_result = await db.execute(
        select(ClusterResult).where(ClusterResult.run_id == run_id).order_by(ClusterResult.cluster_id)
    )
    clusters = list(clusters_result.scalars().all())

    assignments_result = await db.execute(
        select(ChunkClusterAssignment)
        .where(ChunkClusterAssignment.run_id == run_id)
        .options(selectinload(ChunkClusterAssignment.chunk))
    )
    assignments = [
        ChunkAssignmentOut(
            chunk_id=a.chunk_id,
            text=a.chunk.text,
            document_id=a.chunk.document_id,
            page_number=a.chunk.page_number,
            x=a.x,
            y=a.y,
            cluster_id=a.cluster_id,
            bridge_between=a.bridge_between,
        )
        for a in assignments_result.scalars().all()
    ]

    grid_result = await db.execute(
        select(UmapGridResult).where(UmapGridResult.run_id == run_id).order_by(UmapGridResult.score.desc())
    )
    umap_grid = list(grid_result.scalars().all())

    return RunResultsOut(
        run=RunOut.model_validate(run),
        clusters=[ClusterResultOut.model_validate(c) for c in clusters],
        assignments=assignments,
        umap_grid=[UmapGridRowOut.model_validate(g) for g in umap_grid],
    )
