import asyncio
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app import qdrant_store
from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Chunk, ChunkClusterAssignment, ClusterResult, PipelineRun, UmapGridResult
from app.services.clustering import KDEWatershedClusterer
from app.services.embedding import embed_texts
from app.services.experiment_tracking import track_run
from app.services.naming import name_clusters
from app.services.umap_search import grid_search


def start_run(run_id: uuid.UUID) -> None:
    """Kick off pipeline ใน background thread แยกจาก event loop ของ request
    (v1: threading เปล่า ๆ พอสำหรับปริมาณงานตอนนี้ — ถ้า concurrent run เยอะขึ้นค่อยย้ายไป
    task queue จริงเช่น Celery/RQ ตามที่ระบุไว้ใน docs เป็น known tradeoff)
    """
    thread = threading.Thread(target=lambda: asyncio.run(_run_pipeline(run_id)), daemon=True)
    thread.start()


async def _run_pipeline(run_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(PipelineRun, run_id)
        if run is None:
            return
        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        async def set_step(step: str) -> None:
            run.current_step = step
            await db.commit()

        try:
            with track_run(run.project_id, run.id) as tracker:
                await set_step("LOADING_CHUNKS")
                result = await db.execute(
                    select(Chunk).where(Chunk.project_id == run.project_id).order_by(Chunk.chunk_index)
                )
                chunks = list(result.scalars().all())
                if len(chunks) < 5:
                    raise ValueError(f"ต้องการ chunk อย่างน้อย 5 ชิ้นถึงจะจัดกลุ่มได้ (มี {len(chunks)})")

                texts = [c.text for c in chunks]

                tracker.log_params(
                    {
                        "chunk_size": settings.chunk_size,
                        "chunk_overlap": settings.chunk_overlap,
                        "embed_model_name": settings.embed_model_name,
                        "llm_backend": run.llm_backend,
                        "cluster_bw": settings.cluster_bw,
                        "cluster_grid_size": settings.cluster_grid_size,
                        "cluster_neighborhood": settings.cluster_neighborhood,
                        "bridge_window": settings.bridge_window,
                        "n_chunks": len(chunks),
                    }
                )

                await set_step("EMBEDDING")
                vectors = embed_texts(texts, prompt=settings.embed_prompt)

                await set_step("UPSERT_VECTORS")
                qdrant_store.upsert_chunks(
                    project_id=run.project_id,
                    chunk_ids=[c.id for c in chunks],
                    vectors=vectors.tolist(),
                    payloads=[
                        {
                            "chunk_id": str(c.id),
                            "document_id": str(c.document_id),
                            "page_number": c.page_number,
                            "text": c.text,
                        }
                        for c in chunks
                    ],
                )

                await set_step("UMAP_SEARCH")
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

                await set_step("CLUSTERING")
                clusterer = KDEWatershedClusterer(
                    bw_method=settings.cluster_bw,
                    grid_size=settings.cluster_grid_size,
                    neighborhood_size=settings.cluster_neighborhood,
                    bridge_window=settings.bridge_window,
                    bridge_rel_threshold=settings.bridge_rel_threshold_value,
                )
                labels = clusterer.fit_predict(coordinate_xy)

                await set_step("NAMING")
                cluster_names = name_clusters(texts, labels, llm_backend=run.llm_backend)

                n_clusters = len({int(c) for c in labels if c >= 0})
                n_bridge = int((labels == -2).sum())
                n_noise = int((labels == -1).sum())
                tracker.log_metrics(
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

                await set_step("PERSISTING")

                for r in ranking:
                    db.add(
                        UmapGridResult(
                            run_id=run.id,
                            n_neighbors=r["n_neighbors"],
                            min_dist=r["min_dist"],
                            silhouette=r["silhouette"],
                            davies_bouldin=r["davies_bouldin"],
                            entropy=r["entropy"],
                            score=r["score"],
                        )
                    )

                for idx, chunk in enumerate(chunks):
                    cid = int(labels[idx])
                    db.add(
                        ChunkClusterAssignment(
                            run_id=run.id,
                            chunk_id=chunk.id,
                            x=float(coordinate_xy[idx, 0]),
                            y=float(coordinate_xy[idx, 1]),
                            cluster_id=cid,
                            bridge_between=clusterer.bridge_between_.get(idx),
                        )
                    )

                for cid in sorted({int(c) for c in labels if c >= 0}):
                    member_idx = [i for i, lbl in enumerate(labels) if lbl == cid]
                    centroid = coordinate_xy[member_idx].mean(axis=0)
                    db.add(
                        ClusterResult(
                            run_id=run.id,
                            cluster_id=cid,
                            name=cluster_names.get(cid, f"cluster_{cid}"),
                            size=len(member_idx),
                            centroid_x=float(centroid[0]),
                            centroid_y=float(centroid[1]),
                        )
                    )

                run.best_umap_params = {
                    "n_neighbors": best["n_neighbors"],
                    "min_dist": best["min_dist"],
                    "score": best["score"],
                }
                run.status = "DONE"
                run.current_step = "DONE"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as e:  # noqa: BLE001 — pipeline run ที่ fail ต้อง persist สถานะกลับไปให้ผู้ใช้เห็น ไม่ใช่กลืน error
            run.status = "FAILED"
            run.current_step = "FAILED"
            run.error_message = str(e)
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
