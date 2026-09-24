# Risk Map

> `/brownfield --full`. Every entry is confirmed against source with
> `file:line` evidence. Severity reflects blast radius, not effort.
>
> Context that amplifies everything below: **CI runs no tests** (`ci-map.md`),
> and **62% of `app/` modules have no test at all** (`test-map.md`). None of the
> HIGH findings can be caught by the current suite.

---

## HIGH — latent runtime breaks

### R1 — Missing production dependencies break every job application
`app/crawlers/indeed.py:8` — module-level `from bs4 import BeautifulSoup`.
`beautifulsoup4` and `lxml` (used as the parser at `:86`) are **absent from
`requirements.txt`**, which is the only thing `Dockerfile:31` installs.

Blast radius is wider than Indeed: `_crawler_for_portal`
(`app/services/application_service.py:60-76`) eagerly imports `IndeedCrawler`
for *every* portal, so the `ImportError` fires on any apply attempt.
`sentence-transformers` (`app/ml/matcher.py:26`) and `psycopg2`
(`installer/pages/database.py`) are likewise undeclared.

Fix: add `beautifulsoup4`, `lxml`, `sentence-transformers` to
`requirements.txt`; make the crawler imports lazy per-portal.

### R2 — Tenant provisioning never creates tenant tables
`app/database.py:44-47` — `provision_user_schema` runs only
`CREATE SCHEMA IF NOT EXISTS`. Its docstring claims it also "run[s] tenant
migrations"; it does not. `run_tenant_migrations()` exists at
`alembic/env.py:123-145` and is **called from nowhere in the codebase**.

`app/routers/onboarding.py:111-126` provisions the schema and immediately
inserts a `UserProfile` into it — a write into a schema with no tables.
Every new user's onboarding is affected.

Fix: call `run_tenant_migrations(schema_name)` from `provision_user_schema`, or
make onboarding await a provisioning task that does. This is a design decision
(inline vs. async) and belongs in `/spec`, not a patch.

### R3 — Local `alembic/` package shadows the installed Alembic distribution
`alembic/__init__.py` is a 0-byte file that makes the migrations directory an
importable package named `alembic`. With the repo root on `sys.path` — which
root `conftest.py` causes under pytest — `from alembic import op`
(`alembic/versions/0001_initial_shared_schema.py:10`,
`0002_phase4_columns.py:12`) resolves to this empty package and fails.

The coupling report's fan-in of 49 for this file is precisely this shadowing,
from only 3 distinct importers.

Fix: delete `alembic/__init__.py`. The stock Alembic scaffold has none.

### R4 — Divergent crawler registries: Monster/Shine crawlable but not appliable
`app/tasks/crawl_jobs.py:14-19` registers six portals;
`app/services/application_service.py:60-76` registers four. `monster` and
`shine` are valid `PortalName` members (`app/models/portal_account.py:8-15`) and
are on the Celery beat schedule (`app/tasks/celery_app.py:59-67`), so the system
ingests jobs it then raises `ValueError` on when applying.

Fix: one `app/crawlers/registry.py` keyed off the `PortalName` enum so an
unregistered member fails loudly at import. See
`specs/reviews/modularity-review.md`.

---

## HIGH — security

### R5 — `allowed_ips` config implies an admin IP control that does not exist
`app/config.py:84-91` defines `allowed_ips` / `allowed_ip_list`, and
`app/security/ip_allowlist.py:1-15` defines `require_server_ip`. **Neither is
imported anywhere.** No admin route depends on it
(`app/routers/admin/*` use only `get_current_admin`).

This is worse than a missing control: an operator reading `.env.example` will
reasonably believe admin access is IP-restricted when it is not.

Fix: either wire `require_server_ip` into the admin router dependencies, or
delete the setting and the module. Do not leave it implying a guarantee.

### R6 — PII classification policy is documentation, not enforcement
`app/security/pii_policy.py:1-43` declares `ENCRYPTED_FIELDS`, `HASHED_FIELDS`,
`PLAIN_FIELDS`. The module is **never imported**. Nothing checks that a new
model column holding PII is actually encrypted; compliance depends entirely on
each author remembering.

Fix: assert the policy in a test that reflects over `app/models/` and
`app/tenant_models/` columns, so adding an unencrypted PII field fails CI.

### R7 — Tenant schema name is interpolated into SQL
`app/database.py:37` — `SET search_path TO "{schema_name}", public`; `:47` —
`CREATE SCHEMA IF NOT EXISTS "{schema_name}"`.

Currently safe: every call site passes `User.schema_name`, itself produced by
`schema_name_from_thumbprint` (`app/security/encryption.py:29-31`) as
`u_` + 32 hex chars. But the *function* validates nothing, so safety rests on
caller discipline across 20+ call sites.

Fix: validate `^u_[0-9a-f]{32}$` inside `get_tenant_db` / `provision_user_schema`
and raise otherwise. Cheap, local, removes the class of bug permanently.

### R8 — Tenant isolation depends on session setup, not query predicates
By design (`app/database.py:34-41`), per-user queries are unqualified and rely
on `search_path`. A missing or wrong `search_path` therefore reads **another
tenant's rows** rather than erroring. No test asserts isolation
(`test-map.md`).

Fix: add a cross-tenant isolation test — provision two schemas, write to one,
assert the other's session cannot see the row. This is the single highest-value
test in the repo.

### R9 — Insecure-by-default deployment posture
`app/config.py:10` — `app_env` defaults to `"development"`, so `is_production`
(`:115-116`) is False unless explicitly set. Consequences if `APP_ENV` is
unset in production: OpenAPI docs served at `/api/docs` and `/api/redoc`
(`app/main.py:42-43`), and session cookies set with `https_only=False`
(`app/main.py:52-55`).

Fix: default `app_env` to `"production"` and require an explicit opt-in to
development.

**Good practice observed** (do not regress): `app_secret_key`,
`postgres_password`, `minio_secret_key`, and `fernet_key` have **no defaults**
(`app/config.py:11,20,44,49`) — the app fails fast rather than booting with a
known key. Portal credentials and session cookies are Fernet-encrypted at rest
(`app/models/portal_account.py:35-39`).

---

## HIGH — legal / domain

### R10 — Portal automation and anti-detection
`app/crawlers/anti_detection.py` exists specifically to defeat bot detection:
rotating user agents (`:10-17`), randomized viewports (`:19-25`), humanized
delays, typing, and scrolling (`:45-69`), and `configure_stealth_context`
(`:72-79`). The crawlers log into portals with stored credentials and submit
applications autonomously.

Automated login, scraping, and application submission violate the terms of
service of most major job portals. Additionally, `SystemPortalAccount`
credentials are operator-owned and shared across users, which concentrates the
exposure into a small number of accounts.

This is a product and legal decision, not a defect — but it should be an
explicit, owned decision with counsel's input, not an implementation detail
inherited from a scaffold. It materially affects whether this system can be
operated commercially.

### R11 — DPDPA consent machinery is untested
`app/compliance/dpdpa.py` (`ConsentRecord`) and `consent_store.py`
(`record_consent`) are **never referenced by any test**, while
`deletion.py` is. For a system handling Indian personal data under the DPDP
Act, consent capture is the legally load-bearing part.

Fix: cover `record_consent` and assert an audit entry is written for each
consent grant and withdrawal.

---

## MEDIUM — data / operations

### R12 — Irreversible data operations
`app/compliance/deletion.py:35-47` `_hard_delete` and `:68-84` `_anonymise` are
irreversible. `execute_deletion` (`:18`) dispatches on `DeletionMode`. These are
tested (`TestDeletionModes`) but only against mocks — no test proves the tenant
schema is actually dropped or that no orphan rows survive in `public`.

Treat any change here as requiring explicit human approval.

### R13 — Migrations
Two migrations exist (`alembic/versions/0001_initial_shared_schema.py`,
`0002_phase4_columns.py`). `0002`'s docstring notes it must be run per-tenant
with `-x schema=<name>`; there is no runner that iterates tenants. Combined
with R2, tenant schema state is effectively unmanaged.

### R14 — No observability despite manifest claims
`project-manifest.json:82-93` declares `observability.enabled: true`,
`metrics_path: /metrics`, and an SLO of `p95 500ms / 1% errors`. **No `/metrics`
route and no Prometheus dependency exist.** The SLO is unmeasurable, and
`perf-baseline.json` could not be produced during this run (app not running,
Docker unavailable).

The global exception handler (`app/main.py:83-96`) does log stack traces via
structlog and returns an opaque 500 — correct, and the main observability that
does work.

### R15 — Oversized functions will collide with the pre-write gate
50 functions under `app/` exceed this project's own 30-line ceiling
(CLAUDE.md), led by `app/tasks/auto_apply.py:48` `apply_matched_jobs()` at
**219 lines**, `app/tasks/status_check.py:64` (134), `app/tasks/crawl_jobs.py:45`
(117), and `app/services/application_service.py:79` (117). Two files exceed the
300-line ceiling: `app/routers/onboarding.py` (326), `app/crawlers/naukri.py`
(306).

Practical consequence: an agent editing these files may be blocked by the
pre-write gate. Plan extraction before feature work lands there.

### R16 — Obfuscated identity assignment in onboarding
`app/routers/onboarding.py:97-100`:
`thumbprint, schema_name = schema_name_from_thumbprint.__module__ and (...)`.
The `__module__ and` is a no-op truthiness guard that obscures a plain tuple
assignment, on the code path that establishes a user's permanent identity. It
also calls `generate_thumbprint` twice. Rewrite plainly.

### R17 — TOTP verify was an OAuth bypass (fixed, CHG-003)
`POST /api/auth/totp/verify` took `user_id` and `code` as query parameters and
needed no prior authentication. On a valid code it marked the account
2FA-verified and issued an eight-hour `access_token`. That turned a user id plus
a TOTP code into a full session without the OAuth login. SEC-009 in
`specs/reviews/security-review.md` describes it.

Fixed: the OAuth callback's `totp_setup` branch now sets a signed `pending_2fa`
cookie. It is a JWT with `purpose=totp_setup`, lives 10 minutes, and is
`HttpOnly`, `Secure`, `SameSite=Lax`, scoped to `/api/auth/totp`. The verify
endpoint takes only `code`, gets the user from that cookie, and returns 401 when
the cookie is missing, expired, or has the wrong purpose. It clears the cookie
on success. `get_current_user` now refuses any JWT that has a `purpose` claim,
so a pending token cannot be used as a session.

**Still open (product decision):** a user who has verified TOTP once is never
asked for a code at later logins. OAuth alone gets them a session. Whether to
require TOTP at every login has not been decided.

---

## Structural risks

- **Cycles: none.** 0 strongly-connected components across 136 files. Preserve
  this.
- **Hub without tests:** `app/dependencies.py` (22 fan-in, the auth boundary) —
  no test.
- **Unstable hubs:** none meet the fan-in ≥5 + instability ≥0.8 threshold. The
  highest are `app/crawlers/naukri.py` (0.703) and
  `app/services/application_service.py` (0.587).
- **Orphans:** `app/billing/stripe_client.py` and `app/crawlers/company_pages/`
  are unreferenced by any caller or test — genuinely dead today. Most other
  "dead-code candidates" in `coupling-report.md` are **false positives**:
  routers, tasks, and crawlers are wired dynamically (`include_router`,
  `importlib` at `app/tasks/crawl_jobs.py:38-41`).

## Feature flags

`flag-scan.js` detected **no** flags, and no `flag-inventory.md` was written.
That result is incomplete: two in-code runtime toggles behave as flags and the
scanner's SDK/env heuristics miss both —
`SoftSignals.enabled` / `activate_soft_signals()`
(`app/ml/taxonomy_discovery.py:95,113-115`) and `activate_plan(tier)`
(`app/billing/gates.py:31-39`). Both default to off/inactive, so the code paths
behind them are dark in production. Treat them as flags when changing matching
or billing.
