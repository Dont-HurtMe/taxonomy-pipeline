from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://taxonomy:taxonomy@postgres:5432/taxonomy"

    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "taxonomy-documents"
    minio_secure: bool = False

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""

    mlflow_tracking_uri: str = "http://mlflow:5000"

    embed_model_name: str = "BAAI/bge-m3"
    embed_prompt: str = "จงพิจารณาข้อความนี้เพื่อจัดหมวดหมู่ตามประเภทของปัญหาหรือภัยพิบัติ: "
    embed_device: str = ""

    chunk_size: int = 200
    chunk_overlap: int = 20

    umap_n_neighbors: str = "5,10,15"
    umap_min_dist: str = "0.1,0.3"
    probe_bw: float = 0.15
    probe_grid_size: int = 100
    probe_neighborhood: int = 5

    cluster_bw: float = 0.15
    cluster_grid_size: int = 120
    cluster_neighborhood: int = 7
    bridge_window: int = 3
    bridge_rel_threshold: str = ""

    llm_backend: str = "openai"
    dspy_model: str = "openai/gpt-4o-mini"
    openai_api_key: str = ""
    ollama_model: str = "gemma3:27b"
    ollama_host: str = "http://host.docker.internal:11434"

    cors_origins: str = "http://localhost"

    @property
    def umap_n_neighbors_list(self) -> list[int]:
        return [int(v) for v in self.umap_n_neighbors.split(",") if v.strip()]

    @property
    def umap_min_dist_list(self) -> list[float]:
        return [float(v) for v in self.umap_min_dist.split(",") if v.strip()]

    @property
    def bridge_rel_threshold_value(self) -> float | None:
        return float(self.bridge_rel_threshold) if self.bridge_rel_threshold.strip() else None

    @property
    def cors_origins_list(self) -> list[str]:
        return [v.strip() for v in self.cors_origins.split(",") if v.strip()]


settings = Settings()
