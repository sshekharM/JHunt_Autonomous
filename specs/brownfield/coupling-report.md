# Coupling Report

- Files: **136**
- Internal edges: **933**
- External imports: **454**
- Cycles: **0**

## Top hubs (by fan-in)

| File | Fan-in | Fan-out | Instability |
|---|---:|---:|---:|
| `app/security/audit_log.py` | 80 | 0 | 0 |
| `app/database.py` | 78 | 1 | 0.013 |
| `app/crawlers/anti_detection.py` | 68 | 0 | 0 |
| `alembic/__init__.py` | 49 | 0 | 0 |
| `app/crawlers/base.py` | 39 | 0 | 0 |
| `app/billing/gates.py` | 33 | 6 | 0.154 |
| `app/ml/matcher.py` | 32 | 0 | 0 |
| `app/services/job_service.py` | 31 | 3 | 0.088 |
| `app/ml/taxonomy_discovery.py` | 29 | 2 | 0.065 |
| `app/services/__init__.py` | 29 | 0 | 0 |

## Dead-code candidates (no inbound edges)

_Verify dynamic references (`getattr`, registries, entry points) before deleting._

- `alembic/env.py`
- `alembic/versions/0001_initial_shared_schema.py`
- `alembic/versions/0002_phase4_columns.py`
- `app/__init__.py`
- `app/billing/__init__.py`
- `app/billing/stripe_client.py`
- `app/compliance/__init__.py`
- `app/crawlers/__init__.py`
- `app/crawlers/company_pages/__init__.py`
- `app/crawlers/company_pages/base_company.py`
- `app/crawlers/monster.py`
- `app/crawlers/shine.py`
- `app/llm/anthropic_client.py`
- `app/llm/ollama_client.py`
- `app/llm/router.py`
- `app/ml/__init__.py`
- `app/notifications/discord_bot.py`
- `app/notifications/email_client.py`
- `app/notifications/telegram_bot.py`
- `app/routers/admin/config.py`
- … 42 more

