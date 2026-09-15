import uuid

import mlflow
import pandas as pd
from mlflow.artifacts import download_artifacts
from mlflow.entities import Run
from mlflow.tracking import MlflowClient

from app.config import settings

mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
_client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)


def _experiment_name(project_id: uuid.UUID) -> str:
    return f"project-{project_id}"


def get_experiment_id(project_id: uuid.UUID) -> str | None:
    exp = _client.get_experiment_by_name(_experiment_name(project_id))
    return exp.experiment_id if exp is not None else None


def get_run(project_id: uuid.UUID, run_id: str) -> Run | None:
    """คืน None ถ้า run ไม่มีอยู่จริง หรือไม่ได้อยู่ใต้ experiment ของ project_id นี้ (กัน
    run_id ของ project อื่นถูกเรียกดูข้าม project)
    """
    try:
        run = _client.get_run(run_id)
    except Exception:
        return None
    experiment_id = get_experiment_id(project_id)
    if experiment_id is None or run.info.experiment_id != experiment_id:
        return None
    return run


def list_runs(project_id: uuid.UUID) -> list[Run]:
    experiment_id = get_experiment_id(project_id)
    if experiment_id is None:
        return []
    return _client.search_runs(experiment_ids=[experiment_id], order_by=["attributes.start_time DESC"])


def download_artifact_df(project_id: uuid.UUID, run_id: str, filename: str) -> pd.DataFrame | None:
    """โหลด parquet artifact ของ run นี้กลับมาเป็น DataFrame — คืน None ถ้า run ไม่พบ หรือ artifact
    ยังไม่ถูก log (เช่น run ยังไม่ FINISHED)
    """
    if get_run(project_id, run_id) is None:
        return None
    try:
        local_path = download_artifacts(run_id=run_id, artifact_path=filename)
    except Exception:
        return None
    return pd.read_parquet(local_path)
