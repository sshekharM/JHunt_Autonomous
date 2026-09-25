# Review context pack — CHG-001 unified crawler registry

Story: `specs/stories/CHG-001-unified-crawler-registry.md` (AC1–AC5).

## Problem
Beat crawls 6 portals via `crawl_jobs._CRAWLER_MAP`; the apply path
(`application_service._crawler_for_portal`, also used by
`tasks/status_check.py:98`) had its own 4-portal map, so applying to /
status-checking Monster and Shine jobs raised `ValueError`.

## Changed files (uncommitted working tree)
- NEW `app/crawlers/registry.py` — `_REGISTRY`, `SUPPORTED_PORTALS`,
  `is_supported`, `crawler_class_for`, `crawler_for` (lazy importlib).
- `app/services/application_service.py` — `_crawler_for_portal` delegates to
  `registry.crawler_for` (name kept for status_check caller).
- `app/tasks/crawl_jobs.py` — `_CRAWLER_MAP` / `_import_crawler` removed;
  `is_known_portal()` added; crawl uses `crawler_class_for`.
- NEW `tests/unit/test_registry.py`, `tests/unit/test_crawl_jobs.py`.
- Out of review scope: `.claude/hooks/lib/tdd.js` (user-applied harness change).

## Review mode
`review-tier.js` → standard (one code-reviewer). No security boundary crossed
(no auth, routes, persistence, input handling changes).

## Verification (passed)
- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` → 257 passed.
- `uvx ruff check` on new files → clean; touched modules 15 → 14 pre-existing findings.
- `uvx mypy` on touched modules → 6 pre-existing `union-attr` errors in
  `apply_to_job` (`job_record: Optional[object]`), untouched by this diff.
