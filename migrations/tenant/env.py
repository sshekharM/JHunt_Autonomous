"""
Alembic environment for the TENANT chain: tables that live in each user's
private schema (app/tenant_models, TenantBase). The shared public schema has
its own chain in alembic/.

Not run from the alembic CLI. app.tenant_migrations.migrate_tenant_schema()
calls it with an open connection whose search_path is already set to the
tenant schema, passed via config.attributes:
    connection  – sync Connection (inside the caller's transaction)
    schema      – validated tenant schema name (holds alembic_version)
"""
from alembic import context

from app.tenant_migrations import tenant_metadata

if context.is_offline_mode():
    raise RuntimeError("Tenant migrations run online only, via app.tenant_migrations.")

connection = context.config.attributes["connection"]
schema = context.config.attributes["schema"]

def _include_name(name, type_, parent_names) -> bool:
    # alembic_version lives in the tenant schema; never autogenerate ops for it.
    return not (type_ == "table" and name == "alembic_version")


context.configure(
    connection=connection,
    target_metadata=tenant_metadata(),
    version_table_schema=schema,
    compare_type=True,
    include_name=_include_name,
)

with context.begin_transaction():
    context.run_migrations()
