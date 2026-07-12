from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings


engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_tenant_db(schema_name: str):
    """Return a session scoped to a user's private schema."""
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema_name}", public'))
        try:
            yield session
        finally:
            await session.close()


async def provision_user_schema(schema_name: str) -> None:
    """Create a new PostgreSQL schema for a user and run tenant migrations."""
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
