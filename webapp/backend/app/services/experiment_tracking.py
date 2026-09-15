import contextlib
import logging
import uuid

import mlflow

from app.config import settings

logger = logging.getLogger(__name__)

mlflow.set_tracking_uri(settings.mlflow_tracking_uri)


class _NullableTracker:
    """log ไป MLflow แบบ best-effort — ถ้า server เข้าไม่ถึงหรือ log ล้มเหลว ต้องไม่ทำให้
    pipeline run หลักพัง (MLflow เป็น auxiliary experiment tracking ไม่ใช่ dependency ที่จำเป็น
    ต่อความถูกต้องของผลลัพธ์ clustering)
    """

    def __init__(self, active: bool):
        self.active = active

    def log_params(self, params: dict) -> None:
        if not self.active:
            return
        try:
            mlflow.log_params(params)
        except Exception:
            logger.warning("mlflow log_params failed", exc_info=True)

    def log_metrics(self, metrics: dict) -> None:
        if not self.active:
            return
        try:
            mlflow.log_metrics(metrics)
        except Exception:
            logger.warning("mlflow log_metrics failed", exc_info=True)


@contextlib.contextmanager
def track_run(project_id: uuid.UUID, run_id: uuid.UUID):
    active = False
    try:
        mlflow.set_experiment(f"project-{project_id}")
        mlflow.start_run(run_name=str(run_id))
        active = True
    except Exception:
        logger.warning("mlflow unavailable, skip tracking for run %s", run_id, exc_info=True)

    try:
        yield _NullableTracker(active)
    except Exception:
        if active:
            with contextlib.suppress(Exception):
                mlflow.end_run(status="FAILED")
        raise
    else:
        if active:
            with contextlib.suppress(Exception):
                mlflow.end_run(status="FINISHED")
