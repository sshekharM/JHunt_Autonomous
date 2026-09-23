# Concept: app/tenant_models/application.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/tenant_models/application.py` groups **1** file(s) (hub fan-in hint 18).

## Files

- `app/tenant_models/application.py` (hash 8aca5e562bb01a31)

## Symbols

- `ApplicationStatus`
- `ApplicationFailureReason`
- `JobApplication`
- `ApplicationStatusLog`

## Inbound edges (sample)

- app/routers/applications.py → app/tenant_models/application.py (imports)
- app/routers/applications.py → app/tenant_models/application.py (calls)
- app/routers/applications.py → app/tenant_models/application.py (calls)
- app/services/application_service.py → app/tenant_models/application.py (imports)
- app/services/application_service.py → app/tenant_models/application.py (calls)
- app/services/application_service.py → app/tenant_models/application.py (calls)
- app/services/application_service.py → app/tenant_models/application.py (calls)
- app/services/application_service.py → app/tenant_models/application.py (calls)
- app/services/application_service.py → app/tenant_models/application.py (calls)
- app/tasks/auto_apply.py → app/tenant_models/application.py (imports)
- app/tasks/auto_apply.py → app/tenant_models/application.py (calls)
- app/tasks/status_check.py → app/tenant_models/application.py (imports)
- app/tasks/status_check.py → app/tenant_models/application.py (calls)
- app/tasks/status_check.py → app/tenant_models/application.py (calls)
- tests/unit/test_application_service.py → app/tenant_models/application.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
