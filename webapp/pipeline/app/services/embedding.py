import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from app.config import settings

_model: SentenceTransformer | None = None
_model_device: str | None = None


def get_model() -> tuple[SentenceTransformer, str]:
    """Lazy-load + cache SentenceTransformer ต่อ process — โมเดล bge-m3 หนักหลาย GB
    โหลดครั้งเดียวต่อ worker แล้วใช้ซ้ำทุก request แทนโหลดใหม่ทุกครั้ง (สำคัญมากต่อ throughput)

    cuda -> cpu fallback เดียวกับที่ใช้ใน lab/taxonomy_pipeline_demo.ipynb (กัน
    "CUDA error: no kernel image is available for execution on the device" บน GPU รุ่นเก่า)
    """
    global _model, _model_device
    if _model is not None:
        return _model, _model_device

    device = settings.embed_device or ("cuda" if torch.cuda.is_available() else "cpu")
    try:
        model = SentenceTransformer(settings.embed_model_name, device=device)
        if device.startswith("cuda"):
            model.encode(["ทดสอบ"], show_progress_bar=False)
    except RuntimeError:
        device = "cpu"
        model = SentenceTransformer(settings.embed_model_name, device=device)

    _model, _model_device = model, device
    return _model, _model_device


def embed_texts(texts: list[str], prompt: str | None = None, batch_size: int = 32) -> np.ndarray:
    if not texts:
        return np.empty((0, 0))
    model, _ = get_model()
    all_vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors = model.encode(
            batch,
            prompt=prompt or settings.embed_prompt,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        all_vectors.extend(vectors)
    return np.array(all_vectors)
