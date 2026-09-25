# Concept: app/services/application_service.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/services/application_service.py` groups **1** file(s) (hub fan-in hint 19).

## Files

- `app/services/application_service.py` (hash cb9df5998db233ca)

## Symbols

- `_crawler_for_portal`
- `apply_to_job`
- `transition_status`
- `queue_for_hitl`

## Inbound edges (sample)

- app/routers/applications.py → app/services/application_service.py (imports)
- app/routers/applications.py → app/services/application_service.py (calls)
- app/tasks/status_check.py → app/services/application_service.py (imports)
- app/tasks/status_check.py → app/services/application_service.py (imports)
- app/tasks/status_check.py → app/services/application_service.py (calls)
- app/tasks/status_check.py → app/services/application_service.py (calls)
- app/tasks/status_check.py → app/services/application_service.py (calls)
- tests/unit/test_application_service.py → app/services/application_service.py (imports)
- tests/unit/test_application_service.py → app/services/application_service.py (imports)
- tests/unit/test_application_service.py → app/services/application_service.py (imports)
- tests/unit/test_application_service.py → app/services/application_service.py (calls)
- tests/unit/test_application_service.py → app/services/application_service.py (calls)
- tests/unit/test_application_service.py → app/services/application_service.py (calls)
- tests/validation/test_full_validation.py → app/services/application_service.py (imports)
- tests/validation/test_full_validation.py → app/services/application_service.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
