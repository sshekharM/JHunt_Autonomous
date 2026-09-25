# Concept: app/tenant_models/profile.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/tenant_models/profile.py` groups **1** file(s) (hub fan-in hint 24).

## Files

- `app/tenant_models/profile.py` (hash 3a772f30264a46a5)

## Symbols

- `TenantBase`
- `WFHPreference`
- `LLMChoice`
- `NotificationPlatform`
- `StatusCheckFrequency`
- `UserProfile`
- `UserPreferences`

## Inbound edges (sample)

- alembic/env.py → app/tenant_models/profile.py (imports)
- app/routers/applications.py → app/tenant_models/profile.py (imports)
- app/routers/onboarding.py → app/tenant_models/profile.py (imports)
- app/routers/onboarding.py → app/tenant_models/profile.py (calls)
- app/routers/onboarding.py → app/tenant_models/profile.py (calls)
- app/services/notification_service.py → app/tenant_models/profile.py (imports)
- app/tasks/auto_apply.py → app/tenant_models/profile.py (imports)
- app/tasks/auto_apply.py → app/tenant_models/profile.py (imports)
- app/tenant_models/application.py → app/tenant_models/profile.py (imports)
- app/tenant_models/job.py → app/tenant_models/profile.py (imports)
- app/tenant_models/ml_feedback.py → app/tenant_models/profile.py (imports)
- app/tenant_models/notification.py → app/tenant_models/profile.py (imports)
- app/tenant_models/resume.py → app/tenant_models/profile.py (imports)
- app/tenant_models/screening_qa.py → app/tenant_models/profile.py (imports)
- app/tenant_models/skill.py → app/tenant_models/profile.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
