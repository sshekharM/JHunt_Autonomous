import re

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import TextClause, text
from app.config import settings

# Shape produced by app.security.encryption.schema_name_from_thumbprint:
# "u_" + first 32 hex chars of a sha256 hexdigest. Schema names go into DDL and
# SET search_path, which cannot take bind parameters, so validate before use.
_TENANT_SCHEMA_RE = re.compile(r"u_[0-9a-f]{32}")


def validate_schema_name(schema_name: str) -> str:
    """Return schema_name if it is a tenant schema name; raise ValueError otherwise."""
    if not isinstance(schema_name, str) or not _TENANT_SCHEMA_RE.fullmatch(schema_name):
        raise ValueError(f"Invalid tenant schema name: {schema_name!r}")
    return schema_name


def search_path_sql(schema_name: str) -> TextClause:
    """SET search_path for a validated tenant schema (then public)."""
    return text(f'SET search_path TO "{validate_schema_name(schema_name)}", public')


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
    """Declarative base shared by all ORM models (public and tenant)."""


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_tenant_db(schema_name: str):
    """Return a session scoped to a user's private schema."""
    stmt = search_path_sql(schema_name)
    async with AsyncSessionLocal() as session:
        await session.execute(stmt)
        try:
            yield session
        finally:
            await session.close()


async def provision_user_schema(schema_name: str) -> None:
    """Create a new PostgreSQL schema for a user and run tenant migrations."""
    validate_schema_name(schema_name)
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
