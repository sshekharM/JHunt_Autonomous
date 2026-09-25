"""
Alembic environment for the SHARED (public) schema: users, admin_users,
skill_taxonomy, consent_records, jobs, system_portal_accounts.

Per-user tenant schemas have their own chain in migrations/tenant, run by
app.tenant_migrations when a user is provisioned — never from here.

Usage:
    alembic upgrade head

Connects with the app's asyncpg URL (psycopg2 is not a dependency).
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.compliance.dpdpa import ConsentRecord  # noqa: F401
from app.config import settings

# Shared-schema models
from app.database import Base
from app.models import admin, job, portal_account, skill_taxonomy, user  # noqa: F401

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
