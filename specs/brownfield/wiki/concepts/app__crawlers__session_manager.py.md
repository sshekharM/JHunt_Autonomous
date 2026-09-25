# Concept: app/crawlers/session_manager.py

> Deterministic concept page (hash-cached). Not LLM prose.

## Summary

Cluster `app/crawlers/session_manager.py` groups **1** file(s) (hub fan-in hint 16).

## Files

- `app/crawlers/session_manager.py` (hash 602a0910c6541803)

## Symbols

- `_get_redis`
- `_get_browser`
- `get_context`
- `save_session_cookies`
- `load_session_cookies`
- `clear_session`
- `handle_session_expiry`
- `save_crawl_state`
- `load_crawl_state`
- `shutdown`

## Inbound edges (sample)

- app/crawlers/glassdoor.py → app/crawlers/session_manager.py (imports)
- app/crawlers/glassdoor.py → app/crawlers/session_manager.py (calls)
- app/crawlers/glassdoor.py → app/crawlers/session_manager.py (calls)
- app/crawlers/indeed.py → app/crawlers/session_manager.py (imports)
- app/crawlers/indeed.py → app/crawlers/session_manager.py (calls)
- app/crawlers/linkedin.py → app/crawlers/session_manager.py (imports)
- app/crawlers/linkedin.py → app/crawlers/session_manager.py (calls)
- app/crawlers/linkedin.py → app/crawlers/session_manager.py (calls)
- app/crawlers/naukri.py → app/crawlers/session_manager.py (imports)
- app/crawlers/naukri.py → app/crawlers/session_manager.py (calls)
- app/services/application_service.py → app/crawlers/session_manager.py (imports)
- app/services/application_service.py → app/crawlers/session_manager.py (calls)
- app/tasks/crawl_jobs.py → app/crawlers/session_manager.py (imports)
- app/tasks/crawl_jobs.py → app/crawlers/session_manager.py (calls)
- app/tasks/status_check.py → app/crawlers/session_manager.py (imports)

## Citations

Source of truth: `specs/brownfield/code-graph.json`. Prefer `/context` or `nav-query pack` for task-scoped reads.
