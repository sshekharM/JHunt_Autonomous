# Concept: app/dependencies.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/dependencies.py` groups **1** file(s) (hub fan-in hint 22).

## Files

- `app/dependencies.py` (hash 4970a54f3f90b443)

## Symbols

- `get_current_user`
- `get_current_admin`
- `require_role`

## Inbound edges (sample)

- app/routers/admin/config.py → app/dependencies.py (imports)
- app/routers/admin/config.py → app/dependencies.py (calls)
- app/routers/admin/config.py → app/dependencies.py (calls)
- app/routers/admin/crawls.py → app/dependencies.py (imports)
- app/routers/admin/crawls.py → app/dependencies.py (calls)
- app/routers/admin/ops.py → app/dependencies.py (imports)
- app/routers/admin/ops.py → app/dependencies.py (calls)
- app/routers/admin/portals.py → app/dependencies.py (imports)
- app/routers/admin/portals.py → app/dependencies.py (calls)
- app/routers/admin/portals.py → app/dependencies.py (calls)
- app/routers/admin/taxonomy.py → app/dependencies.py (imports)
- app/routers/admin/taxonomy.py → app/dependencies.py (calls)
- app/routers/admin/taxonomy.py → app/dependencies.py (calls)
- app/routers/admin/users.py → app/dependencies.py (imports)
- app/routers/admin/users.py → app/dependencies.py (calls)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
