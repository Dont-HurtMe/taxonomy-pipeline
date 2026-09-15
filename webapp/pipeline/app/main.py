import threading
import uuid

from fastapi import FastAPI
from mlflow.tracking import MlflowClient
from pydantic import BaseModel

from app.config import settings
from app.pipeline_runner import run_pipeline

_client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)

app = FastAPI(title="Taxonomy Pipeline Executor")


class RunTrigger(BaseModel):
    project_id: uuid.UUID
    llm_backend: str | None = None


def _ensure_experiment(project_id: uuid.UUID) -> str:
    """สร้าง (หรือหา) mlflow experiment ของ project นี้ — ตั้ง artifact_location ให้อยู่ใต้
    S3 prefix ที่ key ด้วย project_id ตรง ๆ (`projects/{project_id}/...`) แทน default ของ mlflow
    ที่ key ด้วย experiment_id เพื่อให้ทุก service (mlflow/backend/frontend/qdrant/postgres/minio)
    คุยกันด้วย project_id เดียวกันทั้งระบบ ตามที่ตกลงกันไว้
    """
    name = f"project-{project_id}"
    exp = _client.get_experiment_by_name(name)
    if exp is not None:
        return exp.experiment_id
    try:
        return _client.create_experiment(
            name, artifact_location=f"s3://{settings.mlflow_bucket}/projects/{project_id}"
        )
    except Exception:
        # race: อีก request สร้าง experiment เดียวกันไปพร้อมกัน — อ่านซ้ำแทนพัง
        exp = _client.get_experiment_by_name(name)
        if exp is None:
            raise
        return exp.experiment_id


@app.post("/runs", status_code=202)
async def trigger_run(payload: RunTrigger):
    """สร้าง mlflow run แล้วรัน pipeline จริงใน background thread — คืน run_id ทันที (ไม่รอ pipeline
    จบ) ให้ backend/frontend เอาไป poll สถานะ/ผลลัพธ์จาก mlflow ต่อเป็นหลัก
    """
    experiment_id = _ensure_experiment(payload.project_id)
    llm_backend = payload.llm_backend or settings.llm_backend
    run = _client.create_run(experiment_id, tags={"current_step": "PENDING", "llm_backend": llm_backend})
    run_id = run.info.run_id

    thread = threading.Thread(
        target=run_pipeline, args=(payload.project_id, run_id, llm_backend), daemon=True
    )
    thread.start()

    return {"run_id": run_id}


@app.get("/health")
async def health():
    return {"status": "ok"}
