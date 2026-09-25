"""
Tenant (per-user schema) migrations.

Each user's data lives in a private PostgreSQL schema built from TenantBase
models. Those tables are versioned by a separate Alembic chain in
migrations/tenant (the alembic/ chain covers only the shared public schema).
provision_user_schema() runs this chain for every new user at onboarding.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, MetaData
from sqlalchemy.ext.asyncio import AsyncConnection

from alembic import command

TENANT_SCRIPT_LOCATION = str(Path(__file__).resolve().parent.parent / "migrations" / "tenant")


def tenant_metadata() -> MetaData:
    """TenantBase metadata with every tenant model module imported (registered)."""
    from app.tenant_models import (  # noqa: F401
        application,
        job,
        ml_feedback,
        notification,
        profile,
        resume,
        screening_qa,
        skill,
    )
    return profile.TenantBase.metadata


def tenant_head_revision() -> str:
    """The revision a fully migrated tenant schema is stamped with."""
    head = ScriptDirectory(TENANT_SCRIPT_LOCATION).get_current_head()
    if head is None:
        raise RuntimeError(f"No tenant migrations found in {TENANT_SCRIPT_LOCATION}")
    return head


def _config(connection: Connection, schema_name: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", TENANT_SCRIPT_LOCATION)
    cfg.attributes["connection"] = connection
    cfg.attributes["schema"] = schema_name
    return cfg


def _upgrade_to_head(connection: Connection, schema_name: str) -> None:
    command.upgrade(_config(connection, schema_name), "head")


async def migrate_tenant_schema(conn: AsyncConnection, schema_name: str) -> None:
    """Upgrade a tenant schema to head on conn, inside the caller's transaction."""
    from app.database import search_path_sql

    await conn.execute(search_path_sql(schema_name))  # validates schema_name
    await conn.run_sync(_upgrade_to_head, schema_name)
