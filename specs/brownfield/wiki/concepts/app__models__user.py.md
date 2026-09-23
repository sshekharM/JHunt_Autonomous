# Concept: app/models/user.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/models/user.py` groups **1** file(s) (hub fan-in hint 27).

## Files

- `app/models/user.py` (hash e4699a19e3a1d8f1)

## Symbols

- `OAuthProvider`
- `UserTier`
- `User`

## Inbound edges (sample)

- app/billing/gates.py → app/models/user.py (imports)
- app/compliance/deletion.py → app/models/user.py (imports)
- app/dependencies.py → app/models/user.py (imports)
- app/routers/admin/ops.py → app/models/user.py (imports)
- app/routers/admin/users.py → app/models/user.py (imports)
- app/routers/applications.py → app/models/user.py (imports)
- app/routers/auth.py → app/models/user.py (imports)
- app/routers/auth.py → app/models/user.py (calls)
- app/routers/auth.py → app/models/user.py (calls)
- app/routers/dashboard.py → app/models/user.py (imports)
- app/routers/notifications.py → app/models/user.py (imports)
- app/routers/onboarding.py → app/models/user.py (imports)
- app/services/notification_service.py → app/models/user.py (imports)
- app/tasks/auto_apply.py → app/models/user.py (imports)
- app/tasks/match_jobs.py → app/models/user.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
