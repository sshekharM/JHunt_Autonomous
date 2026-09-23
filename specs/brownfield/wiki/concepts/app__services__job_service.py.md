# Concept: app/services/job_service.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/services/job_service.py` groups **1** file(s) (hub fan-in hint 31).

## Files

- `app/services/job_service.py` (hash 85dde9d0b4baf5ff)

## Symbols

- `store_jobs`
- `get_matched_jobs_for_user`
- `get_unmatched_jobs`
- `mark_jobs_inactive`

## Inbound edges (sample)

- app/tasks/crawl_jobs.py → app/services/job_service.py (imports)
- app/tasks/crawl_jobs.py → app/services/job_service.py (calls)
- app/tasks/match_jobs.py → app/services/job_service.py (imports)
- app/tasks/match_jobs.py → app/services/job_service.py (calls)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)
- tests/unit/test_deduplication.py → app/services/job_service.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
