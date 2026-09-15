import json
import logging
import tempfile
import uuid
from pathlib import Path

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient

from app import qdrant_store
from app.config import settings
from app.db import load_chunks
from app.services.clustering import KDEWatershedClusterer
from app.services.embedding import embed_texts
from app.services.naming import name_clusters
from app.services.umap_search import grid_search

logger = logging.getLogger(__name__)

mlflow.set_tracking_uri(settings.mlflow_tracking_uri)

_MAX_TAG_LEN = 5000  # mlflow tag value length limit
_client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)


def run_pipeline(project_id: uuid.UUID, run_id: str, llm_backend: str) -> None:
    """รันทั้ง pipeline (embed → UMAP search → cluster → naming → log artifact) ใน background thread
    ของ pipeline service — เรียกจาก app.main หลังสร้าง mlflow run (status RUNNING) ไว้แล้ว

    ใช้ `_client.set_tag` (ไม่ใช่ fluent `mlflow.set_tag`) สำหรับ current_step/error_message เพราะ
    ต้องเขียน tag ได้ทั้งตอนอยู่ใน active-run context และตอน except (run จบไปแล้วด้วย status FAILED
    ที่ context manager ของ mlflow.start_run ตั้งให้อัตโนมัติตอน exception หลุดออกจาก with-block) —
    ถ้าเปิด `with mlflow.start_run(run_id=...)` ซ้ำอีกรอบตอน except เพื่อ set_tag ผ่าน fluent API
    จะเซ็ต status กลับเป็น FINISHED ทับ FAILED เดิมโดยไม่ตั้งใจตอน with-block รอบสองปิดแบบไม่มี exception
    """
    try:
        with mlflow.start_run(run_id=run_id):
            _client.set_tag(run_id, "current_step", "LOADING_CHUNKS")
            chunks = load_chunks(project_id)
            if len(chunks) < 5:
                raise ValueError(f"ต้องการ chunk อย่างน้อย 5 ชิ้นถึงจะจัดกลุ่มได้ (มี {len(chunks)})")

            texts = [c["text"] for c in chunks]

            mlflow.log_params(
                {
                    "chunk_size": settings.chunk_size,
                    "chunk_overlap": settings.chunk_overlap,
                    "embed_model_name": settings.embed_model_name,
                    "llm_backend": llm_backend,
                    "cluster_bw": settings.cluster_bw,
                    "cluster_grid_size": settings.cluster_grid_size,
                    "cluster_neighborhood": settings.cluster_neighborhood,
                    "bridge_window": settings.bridge_window,
                    "n_chunks": len(chunks),
                }
            )

            _client.set_tag(run_id, "current_step", "EMBEDDING")
            vectors = embed_texts(texts, prompt=settings.embed_prompt)

            _client.set_tag(run_id, "current_step", "UPSERT_VECTORS")
            qdrant_store.upsert_chunks(
                project_id=project_id,
                chunk_ids=[c["id"] for c in chunks],
                vectors=vectors.tolist(),
                payloads=[
                    {
                        "chunk_id": str(c["id"]),
                        "document_id": str(c["document_id"]),
                        "page_number": c["page_number"],
                        "text": c["text"],
                    }
                    for c in chunks
                ],
            )

            _client.set_tag(run_id, "current_step", "UMAP_SEARCH")
            ranking = grid_search(
                vectors,
                n_neighbors_list=settings.umap_n_neighbors_list,
                min_dist_list=settings.umap_min_dist_list,
                probe_bw=settings.probe_bw,
                probe_grid_size=settings.probe_grid_size,
                probe_neighborhood=settings.probe_neighborhood,
            )
            best = ranking[0]
            coordinate_xy = best["xy"]

            _client.set_tag(run_id, "current_step", "CLUSTERING")
            clusterer = KDEWatershedClusterer(
                bw_method=settings.cluster_bw,
                grid_size=settings.cluster_grid_size,
                neighborhood_size=settings.cluster_neighborhood,
                bridge_window=settings.bridge_window,
                bridge_rel_threshold=settings.bridge_rel_threshold_value,
            )
            labels = clusterer.fit_predict(coordinate_xy)

            _client.set_tag(run_id, "current_step", "NAMING")
            cluster_names = name_clusters(texts, labels, llm_backend=llm_backend)

            n_clusters = len({int(c) for c in labels if c >= 0})
            n_bridge = int((labels == -2).sum())
            n_noise = int((labels == -1).sum())
            mlflow.log_metrics(
                {
                    "best_n_neighbors": best["n_neighbors"],
                    "best_min_dist": best["min_dist"],
                    "best_silhouette": best["silhouette"],
                    "best_davies_bouldin": best["davies_bouldin"],
                    "best_entropy": best["entropy"],
                    "best_score": best["score"],
                    "n_clusters": n_clusters,
                    "n_bridge_points": n_bridge,
                    "n_noise_points": n_noise,
                }
            )

            _client.set_tag(run_id, "current_step", "LOGGING_ARTIFACTS")
            _log_artifacts(chunks, coordinate_xy, labels, clusterer, cluster_names, ranking)

            _client.set_tag(run_id, "current_step", "DONE")
    except Exception as e:  # noqa: BLE001 — ต้องเซ็ต tag ให้ backend/frontend เห็น error ไม่ใช่กลืนเงียบ ๆ
        logger.exception("pipeline run %s failed", run_id)
        _client.set_tag(run_id, "current_step", "FAILED")
        _client.set_tag(run_id, "error_message", str(e)[:_MAX_TAG_LEN])


def _log_artifacts(chunks, coordinate_xy, labels, clusterer, cluster_names, ranking) -> None:
    """เขียนผลลัพธ์ cluster/assignment/umap-grid เป็น parquet แล้ว log เป็น mlflow artifact
    (เก็บใต้ S3 prefix ของ experiment นี้ = projects/{project_id}/... ตามที่ตั้งไว้ตอนสร้าง experiment
    ใน app.main) แทนตาราง Postgres เดิม — backend อ่านกลับผ่าน mlflow.artifacts.download_artifacts()
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        cluster_ids = sorted({int(c) for c in labels if c >= 0})
        clusters_df = pd.DataFrame(
            [
                {
                    "cluster_id": cid,
                    "name": cluster_names.get(cid, f"cluster_{cid}"),
                    "size": len(member_idx),
                    "centroid_x": float(coordinate_xy[member_idx].mean(axis=0)[0]),
                    "centroid_y": float(coordinate_xy[member_idx].mean(axis=0)[1]),
                }
                for cid in cluster_ids
                for member_idx in [[i for i, lbl in enumerate(labels) if lbl == cid]]
            ]
        )
        clusters_df.to_parquet(tmp_path / "clusters.parquet", index=False)

        # bridge_between เดิมเป็น list[int] | None ต่อแถว — เก็บเป็น JSON string เพราะ parquet/arrow
        # จัดการ list column ที่มีทั้ง null และ list ปนกันได้ไม่ตรงไปตรงมาเท่า string column ธรรมดา
        # backend อ่านกลับด้วย json.loads ตอน build ChunkAssignmentOut
        assignments_df = pd.DataFrame(
            {
                "chunk_id": [str(c["id"]) for c in chunks],
                "x": coordinate_xy[:, 0],
                "y": coordinate_xy[:, 1],
                "cluster_id": labels.astype(int),
                "bridge_between": [
                    json.dumps(clusterer.bridge_between_[i]) if i in clusterer.bridge_between_ else None
                    for i in range(len(chunks))
                ],
            }
        )
        assignments_df.to_parquet(tmp_path / "assignments.parquet", index=False)

        umap_grid_df = pd.DataFrame(
            [
                {k: r[k] for k in ("n_neighbors", "min_dist", "silhouette", "davies_bouldin", "entropy", "score")}
                for r in ranking
            ]
        )
        umap_grid_df.to_parquet(tmp_path / "umap_grid.parquet", index=False)

        mlflow.log_artifact(str(tmp_path / "clusters.parquet"))
        mlflow.log_artifact(str(tmp_path / "assignments.parquet"))
        mlflow.log_artifact(str(tmp_path / "umap_grid.parquet"))
