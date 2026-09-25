# Architecture Map

> `/brownfield --full` narrative companion to `specs/brownfield/wiki/WIKI.md`.
> Every dependency claim below cites an edge from `code-graph.json` or a
> `file:line` in source. Producer: `vendored-ast`, 136 Python files, 933
> internal edges, **0 cycles**, 0 scan warnings.
>
> This describes what exists. It is not a redesign.

## What the system is

**jH_ANS — Autonomous Job Hunt System** (`app/main.py:38-43`): a single-deployable
Python 3.12 / FastAPI monolith plus a Celery worker and beat scheduler, sharing
one codebase and one Postgres instance. It crawls Indian job portals, ML-matches
jobs against a user profile, and auto-applies via Playwright browser automation,
with a human-in-the-loop brake.

There is **no web frontend in this repository** (`project-manifest.json`
`stack.frontend: null`). The `installer/` tree is a Tkinter desktop setup wizard
(24 `ext:tkinter` edges), not the product UI. Anything calling itself "web UI"
lives outside this repo or does not yet exist.

## Runtime topology

| Process | Entry point | Role |
|---|---|---|
| `app` | `app/main.py` (uvicorn) | HTTP API, `/api/*` |
| `worker` | `app/tasks/celery_app.py` | Crawl / match / apply / status / retrain |
| `beat` | same | Scheduler (e.g. crawl every 4h per portal) |
| `db` / `redis` / `minio` | `docker-compose.yml:4,21,34` | Postgres, broker, object store |

## Layering

The intended order is `routers → services → (crawlers | ml | billing | compliance) → models → database`,
and the graph confirms it holds: **0 cycles across 136 files**. That is the
single healthiest structural fact about this codebase and is worth defending in
review.

Two leaf utilities are imported almost everywhere and sit below every layer:
`app/security/audit_log.py` (24 distinct importers) and `app/database.py` (25).

> **Fan-in caveat.** `coupling-report.md` counts import *edges*, not distinct
> importing files, which inflates its ranking. `app/billing/gates.py` shows
> fan-in 33 from only **2** importers; `app/ml/matcher.py` 32 from **3**;
> `alembic/__init__.py` 49 from **3**. Use importer counts, not the raw column,
> when judging what is genuinely central.

## Major modules

### `app/routers/` — HTTP surface (11 routers)
All mounted in `app/main.py:65-77` under `/api`. User-facing: `auth`,
`onboarding`, `dashboard`, `notifications`, `applications`. Admin-facing, all
under `/api/admin/*`: `users`, `portals`, `crawls`, `taxonomy`, `config`, `ops`.

Public interface: FastAPI route functions. Invariant: every non-auth route
depends on `get_current_user` / `get_current_admin`. Errors: `HTTPException`,
plus a catch-all at `app/main.py:83-96` that returns an opaque 500.

### `app/dependencies.py` — the authentication boundary
Public interface: `get_current_user`, `get_current_admin`, `require_role`
(`:11-63`). This is the only place identity is established.

Invariants it enforces (`:11-32`): a JWT must be present in the `access_token`
**cookie**; the user must exist and be `is_active`; and `totp_verified` must be
true — 2FA is mandatory, not optional. `get_current_admin` (`:35-52`) reads a
distinct `admin_sub` claim, so a user token cannot be replayed as an admin
token. Errors: 401 for missing/invalid identity, 403 for un-set-up 2FA.

### `app/database.py` — session and tenancy boundary
Public interface: `get_db`, `get_tenant_db(schema_name)`,
`provision_user_schema(schema_name)`, `Base` (`:22-47`).

This is where the system's defining decision lives: **tenancy is
schema-per-user, not row-level**. `get_tenant_db` issues
`SET search_path TO "<schema>", public` (`:37`) and every per-user query then
runs unqualified. Consequence: isolation is enforced by the *session setup*, not
by any predicate in the queries, so a wrong or missing `search_path` silently
reads the wrong tenant rather than failing. See `risk-map.md`.

### `app/security/` — cross-cutting guarantees
- `encryption.py` — Fernet field encryption (`encrypt`/`decrypt`), SHA-256
  lookup hashing, and the identity derivation `generate_thumbprint` /
  `schema_name_from_thumbprint` (`:23-31`). The thumbprint is
  `sha256(email:phone)` and is *the* account identity.
- `audit_log.py` — one 33-line `audit()` function; the most-imported symbol in
  the codebase. Correctly shaped: a narrow contract hiding the write.
- `totp.py`, `rate_limiter.py` (slowapi, wired at `app/main.py:47-48`),
  `ip_allowlist.py`, `pii_policy.py`.

### `app/crawlers/` — portal integration (the external boundary)
`base.py:44-114` defines `BaseCrawler` (ABC) with `login`, `search_jobs`,
`apply`, `check_application_status`, `is_session_valid`, plus the DTOs `RawJob`
and `ApplicationReceipt`. Six implementations exist; **four are wired for
applying** (`app/services/application_service.py:60-76`) and **six for
crawling** (`app/tasks/crawl_jobs.py:14-19`) — a real drift, see `risk-map.md`.

`anti_detection.py` supplies randomized user agents, viewports, humanized
delays/typing/scroll, and per-portal rate limits; `session_manager.py` holds
browser contexts and reuses portal sessions.

### `app/services/` — orchestration
`application_service.py` (apply flow + HITL queueing), `job_service.py`
(store/dedupe/match retrieval), `auth_service.py` (OAuth clients, JWT minting),
`resume_service.py`, `cover_letter_service.py`, `screening_service.py`,
`taxonomy_service.py`, `notification_service.py`, `storage_service.py` (MinIO).

### `app/ml/` — matching
`matcher.py:33-57` `compute_match` dispatches to `_tfidf_match` (scikit-learn)
or `_semantic_match` (sentence-transformers, lazily loaded at `:22-30`), and
`meets_threshold` gates action on the score. `taxonomy_discovery.py` mines
unknown skill terms into an approval queue and hosts `SoftSignals`, a capped
(≤0.05) ranking bonus that is **disabled by default**. `explainer.py`,
`feedback.py` close the loop.

### `app/models/` vs `app/tenant_models/` — the data split
This split *is* the tenancy model and must be preserved in any change:
- `app/models/` → `public` schema: `User`, `AdminUser`, `Job`,
  `SystemPortalAccount`, `SkillTaxonomy`.
- `app/tenant_models/` → per-user schema, `TenantBase` declarative base
  (`profile.py:16-18`): `UserProfile`, `UserPreferences`, `JobApplication`,
  `MatchedJob`, resumes, notifications, screening Q&A, ML feedback.

Putting a model in the wrong base puts the data in the wrong schema.

### `app/tasks/` — autonomous loop
`celery_app.py` holds the beat schedule; `crawl_jobs.py` → `match_jobs.py` →
`auto_apply.py` → `status_check.py` → `notify.py`, with `ml_retrain.py` periodic.
This chain, not the HTTP API, is where the product's autonomy lives.

### `app/billing/` and `app/compliance/`
`gates.py:9-28` answers three entitlement questions (portal count, daily apply
cap, paid-LLM access) against `UserTier`. Only the `free` tier is active;
`pro`/`enterprise` are annotated `inactive — scaffold`
(`app/models/user.py:16-19`). `compliance/` implements DPDPA consent records and
three deletion modes (hard / soft / anonymise).

## Data flow — the core loop

```
beat → crawl_jobs._run_crawl(portal)
     → SystemPortalAccount creds + session_manager context (+ anti_detection)
     → Crawler.search_jobs() → [RawJob]
     → job_service.store_jobs()            [public schema, deduped]
     → match_jobs._run_match_for_user()
     → ml.matcher.compute_match() → MatchedJob   [tenant schema]
     → auto_apply.apply_matched_jobs()
          ├─ billing.gates.can_apply_today()
          ├─ below threshold / HITL → application_service.queue_for_hitl()
          └─ → application_service.apply_to_job()
               → _crawler_for_portal() → Crawler.apply() → ApplicationReceipt
               → JobApplication + append-only ApplicationStatusLog
     → status_check → notify (telegram / discord / email)
```

## External integrations

From graph `ext:` targets and `requirements.txt`: PostgreSQL (`sqlalchemy` 46,
`asyncpg`), Redis/Celery, MinIO, Playwright (10 edges, the portal browser),
`httpx` (7), Anthropic + a local Ollama client (`app/llm/`), Telegram, Discord,
SendGrid, Stripe (`app/billing/stripe_client.py` — present but unreferenced),
`bs4` (6 edges) for HTML parsing, `structlog` (33) for JSON logs.

Authlib drives OAuth social login (`app/services/auth_service.py`), with
providers enumerated in `app/models/user.py:9-13`.

## Deep modules worth preserving

- `app/security/audit_log.py` — one function, 24 importers, zero fan-out. A
  textbook narrow interface over a cross-cutting concern.
- `app/security/encryption.py` — hides Fernet and the identity-derivation rules
  behind five small functions.
- `app/crawlers/base.py` — a genuine deep abstraction: five methods hide six
  wildly different portal scraping implementations.
- `app/billing/gates.py` — three boolean questions hiding tier policy.

## Shallow / suspect modules

- `alembic/__init__.py` — 0 bytes, no responsibility, and actively harmful: it
  shadows the installed Alembic package. Its fan-in 49 is that shadowing, from
  only 3 files.
- `app/services/__init__.py`, `app/crawlers/__init__.py` — empty re-export
  shells that inflate graph fan-in without owning anything.
- `app/llm/router.py` — bucketed as "api" by the path heuristic but it is an LLM
  provider selector, not an HTTP router. Do not treat it as a route module.
- `app/crawlers/monster.py` / `shine.py` — 78% identical clones; see
  `specs/reviews/modularity-review.md`.

## Known architecture/manifest mismatches

| Declared | Actual |
|---|---|
| `evaluation.health_check: /health` | only `/api/health` exists (`app/main.py:78`) |
| `observability.metrics_path: /metrics` | no `/metrics` route, no Prometheus dependency |
| `package_manager: uv` | no `pyproject.toml` / `uv.lock`; `requirements.txt` only |
| `python 3.12` (manifest, Dockerfile) | local interpreter is 3.14.7 |
