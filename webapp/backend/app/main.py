from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_models
from app.routers import documents, projects, runs, search, texts
from app.storage import ensure_bucket

app = FastAPI(title="Taxonomy Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(texts.router)
app.include_router(runs.router)
app.include_router(search.router)


@app.on_event("startup")
async def on_startup() -> None:
    await init_models()
    ensure_bucket()


@app.get("/health")
async def health():
    return {"status": "ok"}
