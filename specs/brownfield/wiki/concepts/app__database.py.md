# Concept: app/database.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/database.py` groups **1** file(s) (hub fan-in hint 78).

## Files

- `app/database.py` (hash 9652c9155b35565b)

## Symbols

- `Base`
- `get_db`
- `get_tenant_db`
- `provision_user_schema`

## Inbound edges (sample)

- alembic/env.py → app/database.py (imports)
- app/compliance/dpdpa.py → app/database.py (imports)
- app/crawlers/session_manager.py → app/database.py (imports)
- app/crawlers/session_manager.py → app/database.py (calls)
- app/crawlers/session_manager.py → app/database.py (calls)
- app/dependencies.py → app/database.py (imports)
- app/models/admin.py → app/database.py (imports)
- app/models/job.py → app/database.py (imports)
- app/models/portal_account.py → app/database.py (imports)
- app/models/skill_taxonomy.py → app/database.py (imports)
- app/models/user.py → app/database.py (imports)
- app/routers/admin/ops.py → app/database.py (imports)
- app/routers/admin/portals.py → app/database.py (imports)
- app/routers/admin/taxonomy.py → app/database.py (imports)
- app/routers/admin/users.py → app/database.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
