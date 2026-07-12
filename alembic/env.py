"""
Alembic environment for jH_ANS.

Two migration modes are supported:

1. Shared schema (default, schema=None):
   Manages the public/shared schema tables: users, admin_users, skill_taxonomy,
   consent_records, jobs, system_portal_accounts.

2. Per-user tenant schema (schema="u_<thumbprint[:32]>"):
   Manages tables inside a specific user's private PostgreSQL schema.
   Pass --x-arg schema=u_<thumbprint> on the command line, or call
   run_tenant_migrations() from application code after provisioning a schema.

Usage examples:
    # Shared schema
    alembic upgrade head

    # Single user schema
    alembic -x schema=u_abc123 upgrade head
"""
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context

from app.config import settings

# Shared-schema models
from app.database import Base
from app.models import user, admin, portal_account, job, skill_taxonomy  # noqa
from app.compliance.dpdpa import ConsentRecord  # noqa

# Tenant-schema models (separate declarative base)
from app.tenant_models.profile import TenantBase
from app.tenant_models import (  # noqa
    profile,
    skill,
    job as tenant_job,
    application,
    ml_feedback,
    notification,
    resume,
    screening_qa,
)

alembic_config = context.config
alembic_config.set_main_option("sqlalchemy.url", settings.sync_database_url)

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# The target schema is passed at runtime via -x schema=<name>
_target_schema: str | None = context.get_x_argument(as_dictionary=True).get("schema")

if _target_schema:
    target_metadata = TenantBase.metadata
else:
    target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """
    Filter which objects Alembic generates migration stanzas for.
    When running in tenant mode only emit objects belonging to TenantBase;
    in shared mode only emit objects belonging to the shared Base.
    """
    return True  # Both metadata sets are already scoped; no filtering needed.


def _configure_for_schema(connection, schema: str | None = None):
    """
    Return the context.configure kwargs appropriate for the target schema.
    Setting include_schemas=True + version_table_schema keeps the alembic_version
    table inside the correct schema rather than landing in public.
    """
    kwargs = dict(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
        compare_server_default=True,
    )
    if schema:
        kwargs["version_table_schema"] = schema
        kwargs["include_schemas"] = True
    return kwargs


def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_target_schema,
        include_schemas=bool(_target_schema),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if _target_schema:
            # Scope the connection to the target schema for the duration of migration
            connection.execute(text(f'SET search_path TO "{_target_schema}", public'))

        context.configure(**_configure_for_schema(connection, _target_schema))

        with context.begin_transaction():
            context.run_migrations()


def run_tenant_migrations(schema_name: str, database_url: str | None = None) -> None:
    """
    Programmatically run all tenant migrations for a newly provisioned user schema.
    Called from app.database.provision_user_schema() after CREATE SCHEMA.

    Args:
        schema_name: The PostgreSQL schema name (e.g. "u_abc123def456...").
        database_url: Sync DSN; defaults to settings.sync_database_url.
    """
    from alembic.config import Config
    from alembic import command
    import os

    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", database_url or settings.sync_database_url)
    cfg.attributes["x_args"] = {"schema": schema_name}

    # Override get_x_argument to return our dict without subprocess call
    from alembic.script import ScriptDirectory
    from alembic.runtime.environment import EnvironmentContext

    command.upgrade(cfg, "head", tag=f"schema:{schema_name}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
