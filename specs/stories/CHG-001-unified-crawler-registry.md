# CHG-001 — Unified crawler registry

## Problem

Celery beat crawls six portals (naukri, linkedin, glassdoor, indeed, monster,
shine) via `app/tasks/crawl_jobs.py::_CRAWLER_MAP`, but the apply path
(`app/services/application_service.py::_crawler_for_portal`, also used by
`app/tasks/status_check.py`) keeps its own four-portal mapping. Monster and
Shine jobs are matched and queued, but applying to them (or checking their
status) raises `ValueError: No crawler registered for portal`.

## Acceptance criteria

1. Every portal scheduled for crawling in the Celery beat schedule resolves to
   a crawler instance through the apply-path lookup (`_crawler_for_portal`).
2. `_crawler_for_portal("monster")` returns a `MonsterCrawler` and
   `_crawler_for_portal("shine")` returns a `ShineCrawler`.
3. The crawl task and the apply path read from one registry module
   (`app/crawlers/registry.py`); the set of portals the crawl task accepts
   equals the set the apply path accepts.
4. Portal lookup is case-insensitive; an unknown portal still raises
   `ValueError` naming the portal.
5. Crawler modules stay lazily imported (no Playwright import at registry
   import time).

## Out of scope

- Changes to individual crawler `apply()` / `search_jobs()` implementations.
- Changes to the beat schedule itself.

## Implementation Status

Status: COMPLETE (uncommitted)
Implemented: 2026-09-23
Files changed:
  - app/crawlers/registry.py (new — shared portal → crawler registry, lazy imports)
  - app/services/application_service.py (`_crawler_for_portal` delegates to registry)
  - app/tasks/crawl_jobs.py (`_CRAWLER_MAP`/`_import_crawler` removed; `is_known_portal`; portal name lower-cased)
Tests added/updated: tests/unit/test_registry.py, tests/unit/test_crawl_jobs.py
AC coverage:
  - AC1: test_every_scheduled_crawl_portal_can_be_applied_to[*]
  - AC2: test_monster_and_shine_resolve_to_their_crawlers
  - AC3: test_registry_covers_every_scheduled_crawl_portal, test_crawl_portal_accepts_every_registry_portal[*], test_crawl_portal_rejects_unknown_portal_without_crawling, test_is_known_portal_matches_the_registry, test_crawl_jobs_has_no_private_portal_map
  - AC4: test_lookup_is_case_insensitive, test_unknown_portal_raises_value_error, test_registry_resolves_classes_without_instantiating, test_crawl_portal_normalises_portal_name_case
  - AC5: test_registry_import_is_lazy (subprocess; asserts no crawler modules and no playwright)
Review: specs/reviews/code-review-verdict.json — CR-001 BLOCK (Playwright via base import) fixed; CR-002 (sys.modules pop) and CR-004 (case normalisation) fixed.
Follow-up (resolved in a separate commit): app/routers/admin/crawls.py:9 kept a third hardcoded portal list (admin-triggered crawls rejected monster/shine). It now uses registry.is_supported and lower-cases the portal; covered by tests/unit/test_crawls.py.
