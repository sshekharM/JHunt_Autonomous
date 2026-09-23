# Change Strategy

> `/brownfield --full`. Lane guidance grounded in `risk-map.md`,
> `test-map.md`, `ci-map.md`, and `specs/reviews/modularity-review.md`.

## The governing constraint

**You cannot currently verify anything.** There is no virtualenv, `pytest` is
not installed, Docker is unavailable, CI runs no tests, and the declared suite
cannot install cleanly (`bs4` undeclared — R1). Every lane below assumes a
green baseline first. Shipping any change before that is unverifiable by
construction.

### Step 0 — establish a baseline (do this before any lane)

1. Add `beautifulsoup4`, `lxml`, `sentence-transformers` to `requirements.txt`.
2. Create the environment and install; get `python -m pytest` to a green run.
3. Delete `alembic/__init__.py` (R3) — otherwise migration imports break under
   pytest.
4. Add a CI job that runs `pytest`, `ruff`, and `mypy`. Today CI enforces only
   gitleaks and Semgrep, so the harness gates are the *only* regression
   guarantee — and they do not run on a PR.

Only after step 0 is the rest of this document actionable.

## Lane selection

| Lane | Use for | Concrete examples here |
|---|---|---|
| `/vibe` | ≤3 files, <150 lines, no auth/API/persistence | Delete `alembic/__init__.py` (R3); rewrite the obfuscated assignment in `onboarding.py:97` (R16) |
| `/change` | One behavior change or bugfix with acceptance criteria | Add the three missing dependencies (R1); unify the crawler registry (R4); validate the schema-name regex (R7); default `app_env` to production (R9) |
| `/refactor` | Structure only, tests stay green | Collapse `monster.py`/`shine.py` into a descriptor-driven crawler; extract `apply_matched_jobs()` (R15); introduce `TenantContext` / `ApplicationDocuments` value objects |
| `/spec` → `/design` → `/auto` | Multi-story work needing design decisions | Tenant provisioning + migration runner (R2); an observability layer to satisfy the declared SLO (R14) |
| **Explicit human approval** | Irreversible or legally weighty | Anything in `app/compliance/deletion.py` (R12); any change to `anti_detection.py` or crawler ToS posture (R10); the shared `SystemPortalAccount` credential model |

## Sequencing

**Wave 1 — make the product work (serial, small `/change` units).**
R1 → R3 → R4 → R7. These are independent, well-understood, and each is
verifiable once step 0 lands. Do them before any feature work: the apply path is
the product's core value and is broken in a clean environment today.

**Wave 2 — close the verification gap (parallel with wave 1).**
The three tests named in `test-map.md`: cross-tenant isolation (R8), the
`app/dependencies.py` auth matrix (401/403/admin-replay), and DPDPA
`record_consent` (R11). These are independent of each other and of wave 1, so
they parallelize cleanly.

**Wave 3 — design work.**
R2 (tenant provisioning) needs a real decision — call
`run_tenant_migrations` inline during onboarding, or provision asynchronously
and gate onboarding on completion. Inline is simpler but puts a DDL migration on
a request path. Take this through `/spec` → `/design`; do not patch it.

**Wave 4 — security posture.**
R5 (wire or delete the IP allowlist) and R6 (enforce the PII policy in a test).
Both are small but change security semantics, so they want review, not `/vibe`.

## Parallelism guidance for `/auto`

`/auto` parallelizes on two axes, and this codebase's structure supports both
unusually well — **0 import cycles** across 136 files, with clean module
boundaries:

- **Within a group:** groups with ≥2 stories fan out to parallel teammates.
- **Across groups:** independent dependency groups run concurrently (up to 3).

Natural independent groups here, derived from the actual import boundaries:
`app/crawlers/*` (portal integration), `app/ml/*` (matching), `app/tasks/*`
(orchestration), `app/routers/*` + `app/services/*` (HTTP surface),
`app/compliance/*` + `app/billing/*` (policy). Shape the dependency graph along
these seams and cross-group `Consumes:` edges stay rare.

The one shared chokepoint to watch: `app/database.py` and
`app/security/audit_log.py` are imported by almost everything (25 and 24
distinct importers). Any story that changes *their signatures* serializes the
whole build — give such a story its own early group and publish the interface
first.

## What not to do

- **Do not redesign the tenancy model.** Schema-per-user is load-bearing and
  pervasive (`app/models/` vs `app/tenant_models/` is the whole split). Fix R2
  within the existing model.
- **Do not "clean up" the dead-code candidates in `coupling-report.md`.** Most
  are dynamically wired (`include_router`, `importlib`) and deleting them breaks
  the app. Only `app/billing/stripe_client.py` and
  `app/crawlers/company_pages/` are genuinely unreferenced.
- **Do not refactor off the raw fan-in column.** It counts edges, not importers;
  `billing/gates.py` looks like a hub at 33 but has 2 importers.
- **Do not generalize the four real crawlers.** Only `monster`/`shine` are
  clones (78%); the rest are 35-53% and genuinely differ.

## CI / harness alignment

`ci-map.md` records the discrepancy: CI enforces **no tests, no lint, no
coverage**, while the harness targets an 80% coverage floor, ruff, and mypy. The
stricter gate should win, and that choice is the user's. Until CI runs the
suite, treat every harness gate as advisory-in-practice — nothing blocks a merge
on GitHub today.

## First safe next steps

1. `node .claude/scripts/context-pack.js --diff --budget 1600 "<goal>"`
2. Read only the returned line ranges; clarify if `confidence` is low.
3. Coverage preflight on the target symbols — expect *zero* existing coverage
   for anything under `app/tasks/`, `app/routers/` (except `applications.py`),
   or `app/dependencies.py`.
4. Impact-scoped regression: `node .claude/scripts/local-regression-gate.js`
