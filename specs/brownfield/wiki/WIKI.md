# Codebase Wiki

> Deterministic, always-current map rendered from `code-graph.json`. No LLM — re-rendered on graph change.

- Producer: `vendored-ast`  ·  Language: `mixed`
- Modules: 136  ·  Edges: 1387  ·  Clusters: 27

## Hubs (most-depended-on)

| Module | fan-in | fan-out |
|---|---|---|
| `py:app/security/audit_log.py` | 80 | 4 |
| `py:app/database.py` | 78 | 4 |
| `py:app/crawlers/anti_detection.py` | 68 | 4 |
| `py:alembic/__init__.py` | 49 | 0 |
| `py:app/crawlers/base.py` | 39 | 5 |
| `py:app/billing/gates.py` | 33 | 6 |
| `py:app/ml/matcher.py` | 32 | 6 |
| `py:app/services/job_service.py` | 31 | 9 |
| `py:app/ml/taxonomy_discovery.py` | 29 | 8 |
| `py:app/services/__init__.py` | 29 | 0 |

### Entry points (no inbound deps)

- `py:alembic/env.py`
- `py:alembic/versions/0001_initial_shared_schema.py`
- `py:alembic/versions/0002_phase4_columns.py`
- `py:app/__init__.py`
- `py:app/billing/__init__.py`
- `py:app/billing/stripe_client.py`
- `py:app/compliance/__init__.py`
- `py:app/crawlers/__init__.py`
- `py:app/crawlers/company_pages/__init__.py`
- `py:app/crawlers/company_pages/base_company.py`
- `py:app/crawlers/monster.py`
- `py:app/crawlers/shine.py`
- `py:app/llm/anthropic_client.py`
- `py:app/llm/ollama_client.py`
- `py:app/llm/router.py`
- `py:app/ml/__init__.py`
- `py:app/notifications/discord_bot.py`
- `py:app/notifications/email_client.py`
- `py:app/notifications/telegram_bot.py`
- `py:app/routers/admin/config.py`
- `py:app/routers/admin/crawls.py`
- `py:app/routers/admin/ops.py`
- `py:app/routers/admin/portals.py`
- `py:app/routers/admin/taxonomy.py`
- `py:app/routers/admin/users.py`

### Cycles

_(none)_

### External dependencies

_(none)_

## Pages

- [`installer/pages/` — 12 module(s)](pages/01-installer-pages.md) — 12 module(s)
- [`tests/unit/` — 12 module(s)](pages/02-tests-unit.md) — 12 module(s)
- [`app/crawlers/` — 10 module(s)](pages/03-app-crawlers.md) — 10 module(s)
- [`app/services/` — 10 module(s)](pages/04-app-services.md) — 10 module(s)
- [`app/tenant_models/` — 9 module(s)](pages/05-app-tenant_models.md) — 9 module(s)
- [`app/tasks/` — 8 module(s)](pages/06-app-tasks.md) — 8 module(s)
- [`app/routers/admin/` — 7 module(s)](pages/07-app-routers-admin.md) — 7 module(s)
- [`app/security/` — 7 module(s)](pages/08-app-security.md) — 7 module(s)
- [`app/llm/` — 6 module(s)](pages/09-app-llm.md) — 6 module(s)
- [`app/models/` — 6 module(s)](pages/10-app-models.md) — 6 module(s)
- [`app/routers/` — 6 module(s)](pages/11-app-routers.md) — 6 module(s)
- [`app/` — 5 module(s)](pages/12-app.md) — 5 module(s)
- [`app/ml/` — 5 module(s)](pages/13-app-ml.md) — 5 module(s)
- [`installer/core/` — 5 module(s)](pages/14-installer-core.md) — 5 module(s)
- [`app/billing/` — 4 module(s)](pages/15-app-billing.md) — 4 module(s)
- [`app/compliance/` — 4 module(s)](pages/16-app-compliance.md) — 4 module(s)
- [`app/notifications/` — 4 module(s)](pages/17-app-notifications.md) — 4 module(s)
- [`alembic/` — 2 module(s)](pages/18-alembic.md) — 2 module(s)
- [`alembic/versions/` — 2 module(s)](pages/19-alembic-versions.md) — 2 module(s)
- [`app/crawlers/company_pages/` — 2 module(s)](pages/20-app-crawlers-company_pages.md) — 2 module(s)

## Agent navigation

- Context pack: `node .claude/scripts/nav-query.js pack --budget 1600 "<question>"`
- Refresh secondary indexes: `node .claude/scripts/nav-query.js refresh`

_+ 7 smaller cluster(s) not paged (raise --max-pages)._
