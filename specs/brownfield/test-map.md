# Test Map

> `/brownfield --full` test inventory. Static analysis only — see "Could not
> execute" below.

## Commands

| Purpose | Command | Notes |
|---|---|---|
| Declared (CLAUDE.md) | `cd backend && uv run pytest -x -q` | **Wrong for this repo** — there is no `backend/` directory and no `uv` project |
| Actual | `python -m pytest` | `pytest.ini`: `testpaths = tests`, `asyncio_mode = auto` |
| Lint (declared) | `uv run ruff check --fix .` | ruff is not in `requirements.txt`; not run in CI |
| Types (declared) | `uv run mypy src/` | **No `src/` directory exists**; mypy not in `requirements.txt` |

`pytest.ini` sets `asyncio_mode = auto`, so async tests need no marker.

## Could not execute

The suite was **not run** during discovery. There is no virtualenv, `pytest` is
not installed in the available interpreter (Python 3.14.7; the project targets
3.12), and Docker is unavailable on this machine. Every statement below is from
reading the tests, not from a green run.

Independently, the suite **cannot pass from a clean `requirements.txt` install**:
`tests/validation/test_full_validation.py:30` imports `bs4`, which is not a
declared dependency (see `risk-map.md`, finding R1).

## Inventory

| Location | Files | Tests | Kind |
|---|---|---|---|
| `tests/unit/` | 9 | 80 | Unit, mocked |
| `tests/validation/` | 1 (1448 lines) | 128 | Unit/component, fully mocked |
| `tests/integration/` | `__init__.py` only | **0** | — |
| `e2e/` | empty directory | **0** | — |

Total: **208 tests, all mocked.** The validation file's own docstring states
"All external dependencies (DB, network, Docker) are mocked."

## What is covered

`tests/validation/test_full_validation.py` is organized into 25 classes with
reasonable assertions: `TestEncryption`, `TestThumbprint`, `TestTOTP`,
`TestAuditLog`, `TestComputeMatch`, `TestExplainer`, `TestSoftSignals`,
`TestBillingGates`, `TestDeletionModes`, `TestNotificationService`, per-portal
crawler HTML parsing (`TestNaukriCrawlerParsing`, `TestIndeedCrawlerParsing`),
and installer helpers.

`tests/unit/` adds `test_matching.py` (23), `test_deduplication.py` (13),
`test_billing_gates.py` (8), `test_applications_router.py` (7),
`test_soft_signals.py` (7), `test_application_service.py` (6),
`test_notification_service.py` (5), `test_resume_service.py` (5),
`test_encryption.py` (3), `test_totp.py` (3).

The pure-function core — matching, encryption, TOTP, billing gates, dedup,
soft-signal capping — is genuinely well covered.

## What is not covered

**48 of 78 `app/` modules (62%) are never referenced by any test.** The gaps are
not peripheral; they are the system's boundaries:

| Area | Untested modules |
|---|---|
| **Auth boundary** | `app/dependencies.py` (`get_current_user`, `get_current_admin`, `require_role`), `app/routers/auth.py`, `app/services/auth_service.py` |
| **Entire autonomous loop** | `app/tasks/` — `auto_apply.py`, `crawl_jobs.py`, `match_jobs.py`, `status_check.py`, `ml_retrain.py`, `celery_app.py` |
| **All routers but one** | `onboarding`, `dashboard`, `notifications`, and all six `admin/*`. Only `applications.py` has tests |
| **Tenancy** | no test provisions a schema or asserts cross-tenant isolation |
| **Portal session handling** | `session_manager.py`, `anti_detection.py`, `base.py` |
| **Outbound integrations** | `telegram_bot`, `discord_bot`, `email_client`, `anthropic_client`, `ollama_client`, `llm/router`, `storage_service` (MinIO), `stripe_client` |
| **Compliance** | `consent_store.py`, `dpdpa.py` (DPDPA consent records) — only `deletion.py` is tested |
| **Unwired clones** | `monster.py`, `shine.py` |

## Misleading test name

`TestEndToEndAutonomousLoop` (`tests/validation/test_full_validation.py:1384`)
is **not** end-to-end. `_run_loop()` (`:1394-1411`) builds three hardcoded job
dicts in memory and calls `compute_match` on them. There is no crawl, no
database, no application submission. It asserts ranking order only.

This matters for risk assessment: a green run of this class does **not** mean
the autonomous pipeline works. The four high-severity defects in `risk-map.md`
all sit in code this suite never touches.

## Test isolation

Good practice observed: both `tests/unit/conftest.py` and the validation module
(`:9-19`) bootstrap `APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `MINIO_SECRET_KEY`,
and a freshly generated `FERNET_KEY` via `os.environ.setdefault` *before* any
`app` import — necessary because `app/security/encryption.py:5` constructs the
Fernet instance at module import time. Tests will not silently pick up a
developer's real `.env`.

## CI reality

`.github/workflows/` runs **gitleaks and Semgrep only** — no pytest, no linter,
no typechecker, no coverage. `deploy.yml` is a placeholder echo. See `ci-map.md`.
No regression is caught by CI today.

## Recommended first moves

1. Create the environment: add `beautifulsoup4`, `lxml`, `sentence-transformers`
   to `requirements.txt`, then `pip install -r requirements.txt` and get a
   baseline green run. Until this happens no other test claim is verifiable.
2. Add a **real** integration test that provisions a tenant schema against a
   live Postgres and round-trips a `UserProfile`. This single test would have
   caught `risk-map.md` R2.
3. Add router tests for `app/dependencies.py` covering: no cookie → 401,
   `totp_verified = False` → 403, user token used on an admin route → 401.
4. Add a CI job that actually runs `pytest`.
