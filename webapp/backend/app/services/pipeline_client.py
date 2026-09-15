import uuid

import httpx

from app.config import settings


class PipelineUnavailableError(Exception):
    pass


async def trigger_run(project_id: uuid.UUID, llm_backend: str | None) -> str:
    """เรียก pipeline service ให้เริ่มรัน embed→UMAP→cluster→naming เอง คืน mlflow run_id ที่ backend
    ใช้ poll สถานะ/ผลลัพธ์ต่อจาก mlflow เป็นหลัก (services/mlflow_client.py) — ไม่มี retry/backoff
    เพราะเป็น single trigger call เดียวตอนกดปุ่ม ไม่ใช่ dependency ที่ request อื่นต้องรอซ้ำ ๆ
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.pipeline_url}/runs",
                json={"project_id": str(project_id), "llm_backend": llm_backend},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise PipelineUnavailableError(str(e)) from e
    return resp.json()["run_id"]
