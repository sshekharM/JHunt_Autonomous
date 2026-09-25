# Review Context Pack — /gate fix/admin-ip-allowlist

- **Branch:** fix/admin-ip-allowlist
- **Range:** `7c1cc13..9e364c2` (commits ca539f1..9e364c2)
- **Story/risks:** CHG-002 (`specs/stories/CHG-002-admin-ip-allowlist.md`), risk-map items R5, R6, R9, R11, R16 (`specs/brownfield/risk-map.md`)

## Commits
| SHA | Summary |
|-----|---------|
| ca539f1 | fix(security): enforce ALLOWED_IPS on every admin router (R5) |
| e4f58b7 | fix(security): default APP_ENV to production (R9) |
| 02f3044 | test(security): enforce the PII policy over every model column (R6) |
| 37ce5a0 | feat(compliance): audit DPDPA consent grants and cover record_consent (R11) |
| ac46fda | fix(deploy): trust nginx forwarded headers so the admin allowlist sees clients |
| 70e723f | test(onboarding): pin every onboarding handler before refactoring |
| 9e364c2 | refactor(onboarding): assign thumbprint and schema name plainly (R16) |

## Acceptance criteria (summary)
- R5: every `/api/admin/*` router rejects non-allowlisted client IPs with 403 before auth/role checks; empty `ALLOWED_IPS` fails closed; missing client address denied.
- R9: `APP_ENV` unset => production; only `development|production` accepted; dev compose opts in explicitly.
- R6: every model column that looks like PII is encrypted/hashed or a reviewed exception; known violations (`totp_secret`) listed and cannot spread.
- R11: `record_consent` emits a `consent.granted` audit event without IP/user agent.
- Prod: uvicorn trusts `X-Forwarded-For` only from nginx at fixed 172.28.0.10.
- R16: behavior-preserving refactor of thumbprint/schema derivation in onboarding step 1 (pinned by tests first).

## Changed production files
app/compliance/consent_store.py, app/config.py, app/routers/admin/{config,crawls,ops,portals,taxonomy,users}.py, app/routers/onboarding.py, app/security/ip_allowlist.py, app/security/pii_policy.py, docker-compose.yml, docker-compose.prod.yml, .env.example

## Changed tests
tests/unit/test_admin_config_ops.py, test_config.py, test_consent_store.py, test_ip_allowlist.py, test_onboarding.py, test_pii_policy.py

## Deterministic results
- **pytest:** `.venv/Scripts/python.exe -m pytest -q` -> exit 0, 454 passed, 10 skipped.
- **ruff / mypy:** not installed in `.venv` — NOT RUN.
- **Runtime (docker compose):** Docker unavailable — no runtime/Playwright evaluation possible.
- **Registry gate checks** (`run-gate-checks.js`): cycle, coupling, duplication, observability OK; **perf-smell BLOCK** — 5x PERF-N1-LOOP-QUERY in `app/routers/onboarding.py` (lines 147/169/259/277/306). All flagged lines are pre-existing (diff touched only lines 94-100) and are `async for tenant_db in get_tenant_db(...)` single-yield dependency generators, not N+1 loops — likely false positive. 2x WARN unbounded load (admin ops/portals, pre-existing).

## Risk triggers
Security trigger **FIRED**: auth/authz (admin IP allowlist), middleware/proxy trust (uvicorn forwarded headers, nginx), config defaults, PII/persistence policy, compliance audit logging, API routers.
