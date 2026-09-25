# Codebase Map

Top-level directory structure with one-line descriptions. Helps Claude navigate without scanning.

## Directories

| Directory | Purpose |
|-----------|---------|
| `app/` | FastAPI application source |
| `app/routers/` | HTTP route handlers |
| `app/services/` | Business logic layer |
| `app/models/`, `app/tenant_models/` | SQLAlchemy ORM models (shared + per-tenant) |
| `app/schemas/` | Pydantic request/response schemas |
| `app/crawlers/` | Job-board crawlers (Playwright-based) |
| `app/llm/`, `app/ml/` | Anthropic LLM integration and scikit-learn matching |
| `app/tasks/` | Celery background tasks |
| `app/notifications/` | Telegram / Discord / SendGrid notifiers |
| `app/billing/`, `app/compliance/`, `app/security/` | Billing, compliance and auth/security concerns |
| `alembic/` | Database migrations |
| `tests/` | Unit and integration tests |
| `installer/` | Windows setup wizard |
| `nginx/` | Reverse-proxy config |
| `e2e/` | Playwright end-to-end tests |
| `specs/` | BRD, stories, design docs, brownfield maps |
| `.claude/` | Harness agents, skills, hooks, state |

## Entry Points

- **API**: `app/main.py` (FastAPI app)
- **Worker**: `Dockerfile.worker` (Celery)

## Test Commands

| Scope | Command |
|-------|---------|
| Unit / integration | `pytest -x -q` |
| Lint | `ruff check --fix .` |
| Types | `mypy app/` |
| Migrations | `alembic upgrade head` |
| Full stack | `docker compose up -d --build` |
