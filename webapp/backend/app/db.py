from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_models() -> None:
    # v1: create_all แทน migration tool (Alembic) — เร็ว/ง่ายสำหรับ prototype, ไม่มี migration history
    # ถ้า schema เริ่มเปลี่ยนบ่อยตอน production ค่อยสลับไป Alembic
    async with engine.begin() as conn:
        from app import models  # noqa: F401  ensure models registered on Base.metadata

        await conn.run_sync(Base.metadata.create_all)
