import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings

_client = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    return _client


def _collection_name(project_id: uuid.UUID) -> str:
    # ต้องตรงกับ backend/app/qdrant_store.py เป๊ะ ๆ — สอง service เขียน/อ่านคนละฝั่งของ
    # collection เดียวกัน (pipeline upsert ตอน run, backend search ตอน query)
    return f"project_{project_id}"


def ensure_collection(project_id: uuid.UUID, vector_size: int) -> str:
    name = _collection_name(project_id)
    client = get_client()
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )
    return name


def upsert_chunks(
    project_id: uuid.UUID,
    chunk_ids: list[uuid.UUID],
    vectors: list[list[float]],
    payloads: list[dict],
) -> None:
    if not chunk_ids:
        return
    name = ensure_collection(project_id, vector_size=len(vectors[0]))
    points = [
        qmodels.PointStruct(id=str(cid), vector=vec, payload=payload)
        for cid, vec, payload in zip(chunk_ids, vectors, payloads)
    ]
    get_client().upsert(collection_name=name, points=points)
