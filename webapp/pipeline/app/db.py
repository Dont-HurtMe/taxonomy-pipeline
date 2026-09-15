import uuid

from sqlalchemy import create_engine, text

from app.config import settings

_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)


def load_chunks(project_id: uuid.UUID) -> list[dict]:
    """อ่าน chunk ของ project ตรง ๆ ด้วย raw SQL แทน ORM model เต็มชุด — service นี้อ่านอย่างเดียว
    ไม่เคยเขียน Document/Chunk/Project (เจ้าของข้อมูลจริงคือ backend) จึงไม่ต้อง mirror
    relationship ทั้งชุดมาที่นี่ แค่ column ที่ pipeline ต้องใช้จริงพอ
    """
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, document_id, page_number, text FROM chunks "
                "WHERE project_id = :project_id ORDER BY chunk_index"
            ),
            {"project_id": str(project_id)},
        ).mappings().all()
    return [dict(r) for r in rows]
