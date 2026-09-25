# Codebase map (human homepage)

> Living orientation document. Deterministically rendered from the code-graph + CONTEXT.
> Prefer this page + concept wiki over opening the whole tree.

## What this system is

This project was scaffolded with **Claude Harness Engine v5**.

_Source: `README.md`_

## At a glance

| Metric | Value |
|---|---|
| Indexed files | 136 |
| Graph edges | 1387 |
| Concept pages | 20 |
| Wiki cluster pages | 20 |

## How to run / test / gate

```bash
# project-specific — see README / init.sh
./init.sh                 # or docker compose up
npm test                 # or pytest / vitest
/gate                    # pre-merge quality gate
npm run quality-card     # trust receipt
npm run ask -- "..."     # ask the codebase
```

## Architecture (hub modules)

| Module | fan-in | fan-out |
|---|---|---|
| `app/security/audit_log.py` | 80 | 0 |
| `app/database.py` | 78 | 1 |
| `app/crawlers/anti_detection.py` | 68 | 0 |
| `alembic/__init__.py` | 49 | 0 |
| `app/crawlers/base.py` | 39 | 0 |
| `app/billing/gates.py` | 33 | 6 |
| `app/ml/matcher.py` | 32 | 0 |
| `app/services/job_service.py` | 31 | 3 |
| `app/ml/taxonomy_discovery.py` | 29 | 2 |
| `app/services/__init__.py` | 29 | 0 |
| `app/models/user.py` | 27 | 1 |
| `app/security/encryption.py` | 27 | 1 |

## Entry points

- `app/main.py`
- `app/tasks/celery_app.py`

## Concept pages (clusters)

- [app/security/audit_log.py](specs/brownfield/wiki/concepts/app__security__audit_log.py.md)
- [app/database.py](specs/brownfield/wiki/concepts/app__database.py.md)
- [app/crawlers/anti_detection.py](specs/brownfield/wiki/concepts/app__crawlers__anti_detection.py.md)
- [alembic/__init__.py](specs/brownfield/wiki/concepts/alembic____init__.py.md)
- [app/crawlers/base.py](specs/brownfield/wiki/concepts/app__crawlers__base.py.md)
- [app/billing/gates.py](specs/brownfield/wiki/concepts/app__billing__gates.py.md)
- [app/ml/matcher.py](specs/brownfield/wiki/concepts/app__ml__matcher.py.md)
- [app/services/job_service.py](specs/brownfield/wiki/concepts/app__services__job_service.py.md)
- [app/ml/taxonomy_discovery.py](specs/brownfield/wiki/concepts/app__ml__taxonomy_discovery.py.md)
- [app/services/__init__.py](specs/brownfield/wiki/concepts/app__services____init__.py.md)
- [app/models/user.py](specs/brownfield/wiki/concepts/app__models__user.py.md)
- [app/security/encryption.py](specs/brownfield/wiki/concepts/app__security__encryption.py.md)
- [app/config.py](specs/brownfield/wiki/concepts/app__config.py.md)
- [app/tenant_models/profile.py](specs/brownfield/wiki/concepts/app__tenant_models__profile.py.md)
- [app/dependencies.py](specs/brownfield/wiki/concepts/app__dependencies.py.md)
- [app/services/application_service.py](specs/brownfield/wiki/concepts/app__services__application_service.py.md)
- [app/routers/applications.py](specs/brownfield/wiki/concepts/app__routers__applications.py.md)
- [app/tenant_models/application.py](specs/brownfield/wiki/concepts/app__tenant_models__application.py.md)
- [app/crawlers/session_manager.py](specs/brownfield/wiki/concepts/app__crawlers__session_manager.py.md)
- [app/crawlers/indeed.py](specs/brownfield/wiki/concepts/app__crawlers__indeed.py.md)

## DeepWiki cluster pages

- [01-installer-pages](specs/brownfield/wiki/pages/01-installer-pages.md)
- [02-tests-unit](specs/brownfield/wiki/pages/02-tests-unit.md)
- [03-app-crawlers](specs/brownfield/wiki/pages/03-app-crawlers.md)
- [04-app-services](specs/brownfield/wiki/pages/04-app-services.md)
- [05-app-tenant_models](specs/brownfield/wiki/pages/05-app-tenant_models.md)
- [06-app-tasks](specs/brownfield/wiki/pages/06-app-tasks.md)
- [07-app-routers-admin](specs/brownfield/wiki/pages/07-app-routers-admin.md)
- [08-app-security](specs/brownfield/wiki/pages/08-app-security.md)
- [09-app-llm](specs/brownfield/wiki/pages/09-app-llm.md)
- [10-app-models](specs/brownfield/wiki/pages/10-app-models.md)
- [11-app-routers](specs/brownfield/wiki/pages/11-app-routers.md)
- [12-app](specs/brownfield/wiki/pages/12-app.md)
- [13-app-ml](specs/brownfield/wiki/pages/13-app-ml.md)
- [14-installer-core](specs/brownfield/wiki/pages/14-installer-core.md)
- [15-app-billing](specs/brownfield/wiki/pages/15-app-billing.md)
- [16-app-compliance](specs/brownfield/wiki/pages/16-app-compliance.md)
- [17-app-notifications](specs/brownfield/wiki/pages/17-app-notifications.md)
- [18-alembic](specs/brownfield/wiki/pages/18-alembic.md)
- [19-alembic-versions](specs/brownfield/wiki/pages/19-alembic-versions.md)
- [20-app-crawlers-company_pages](specs/brownfield/wiki/pages/20-app-crawlers-company_pages.md)

## Critical paths & debugging

- Metrics path: `/metrics`
- SLO: error_rate_pct≤1 · p95_ms≤500
- Prefer structured logs with `request_id` / `X-Request-ID` correlation.
- Quality receipt after changes: `specs/reviews/quality-card.md`.
- Ask navigation: `npm run ask -- "where is auth validated?"`.

## If X breaks, start here

| Symptom | Start |
|---|---|
| Auth / session failures | concept or entry modules matching `auth` / `session` |
| Slow API | quality-card perf + `/metrics` + N+1 smells (`npm run perf-smell`) |
| Silent failures | structured logs + `request_id`; observability gate |
| Merge confidence | `specs/reviews/quality-card.md` + `walkthrough.md` |
| "Where is X?" | `npm run ask -- "X"` |

## Machine-readable companions

- `specs/brownfield/code-graph.json` — dependency DAG (agents + tools)
- `specs/brownfield/symbol-map.md` — symbols with line ranges
- `specs/brownfield/wiki/WIKI.md` — deterministic DeepWiki index
- `.harness/wiki.json` — steer wiki priorities (Devin `.devin/wiki.json` analogue)
