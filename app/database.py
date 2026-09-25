import re

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy import TextClause, event, text
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
    return text(f'SET search_path TO "{validate_schema_name(schema_name)}", public')  # nosemgrep -- validated identifier


engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    # Tenants share table names but not types: a statement prepared under one
    # tenant's search_path binds that schema's enum types, and reusing it for
    # another tenant fails. Disable asyncpg's per-connection statement cache.
    connect_args={"prepared_statement_cache_size": 0},
)


@event.listens_for(engine.sync_engine, "checkin")
def _reset_search_path(dbapi_connection, connection_record) -> None:
    """Drop any tenant search_path before a connection goes back to the pool,
    so the next session (tenant or shared) cannot read the previous tenant's tables."""
    if dbapi_connection is None:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("RESET search_path")
    finally:
        cursor.close()

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


_TENANT_SCHEMA_KEY = "tenant_schema"


def tenant_session(schema_name: str) -> AsyncSession:
    """A session scoped to a user's private schema for every transaction it runs.

    AsyncSession returns its connection to the pool on each commit (where the
    search_path is reset), so the schema is applied per transaction with
    SET LOCAL by _scope_transaction_to_tenant, not once per session.
    """
    return AsyncSessionLocal(info={_TENANT_SCHEMA_KEY: validate_schema_name(schema_name)})


@event.listens_for(Session, "after_begin")
def _scope_transaction_to_tenant(session, transaction, connection) -> None:
    schema_name = session.info.get(_TENANT_SCHEMA_KEY)
    if schema_name is not None:
        connection.execute(text(f'SET LOCAL search_path TO "{validate_schema_name(schema_name)}", public'))  # nosemgrep -- validated identifier


async def get_tenant_db(schema_name: str):
    """Yield a tenant_session for a user's private schema."""
    async with tenant_session(schema_name) as session:
        try:
            yield session
        finally:
            await session.close()


async def provision_user_schema(schema_name: str) -> None:
    """Create a new PostgreSQL schema for a user and run tenant migrations."""
    validate_schema_name(schema_name)
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))  # nosemgrep -- validated above
