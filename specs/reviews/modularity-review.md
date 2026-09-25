# Modularity Review

Source: `specs/brownfield/modularity-pack.md` (25 hubs, 0 cycles, 3 duplication
candidates), judged against source during `/brownfield --full`.

> **Provenance caveat:** this pass was performed inline by the brownfield
> planner, not by the dedicated `modularity-reviewer` agent (no Agent tool was
> available in this run). Findings below are all confirmed against source with
> `file:line` evidence, but a second adversarial pass by the real agent is still
> worth running before any large refactor is scheduled.

Verdict: **CONCERNS** (3 high-severity findings).

---

## 1. Duplication

### HIGH — `monster.py` and `shine.py` are 78% identical clones
Evidence: `app/crawlers/monster.py:1-181` vs `app/crawlers/shine.py:1-179`
(line-level `difflib` similarity 78%; the diff is confined to base URL,
`portal_name`, logger name, the two credential settings, and two CSS selector
strings).

These are not "similar because they implement the same ABC" — they are a
copy-paste pair. Every other crawler pair scores 35-53%, which is the genuine
shared shape imposed by `BaseCrawler`.

Fix: collapse both into a single `GenericPortalCrawler(BaseCrawler)`
parameterized by a `PortalDescriptor` dataclass (`base_url`, `portal_name`,
`login_path`, `email_selector`, `password_selector`, `submit_selector`,
`credentials`). Register `monster` and `shine` as two descriptor instances.
Do **not** extend this to Naukri/LinkedIn/Glassdoor/Indeed — their scraping and
apply logic genuinely diverge, and forcing them into a descriptor would create
a configuration language instead of code.

### HIGH — two divergent crawler registries
Evidence: `app/tasks/crawl_jobs.py:14-19` (six portals) vs
`app/services/application_service.py:60-76` (four portals).

The same concept — "which class handles this portal" — is encoded twice and has
already drifted. Monster and Shine are crawled on the beat schedule and are
valid `PortalName` values (`app/models/portal_account.py:8-15`), but applying to
them raises `ValueError`.

Fix: single registry module (`app/crawlers/registry.py`) exporting
`crawler_for_portal(portal: PortalName) -> BaseCrawler`, keyed off the
`PortalName` enum so a new enum member fails loudly at import if unregistered.
Both call sites consume it.

### FALSE POSITIVE — `installer/pages/install.py` + `prerequisites.py`
The pack flagged these on "same imports". Line-level similarity is below 35%;
they share a wizard-page base class and therefore the same imports, but their
bodies differ. No action.

---

## 2. Misplaced responsibility

### HIGH — `alembic/__init__.py` makes the migrations directory a package
Evidence: `alembic/__init__.py` (0 bytes); consumers at `alembic/env.py:25`,
`alembic/versions/0001_initial_shared_schema.py:10`,
`alembic/versions/0002_phase4_columns.py:12` (`from alembic import op/context`).

This file has no responsibility at all — it exists only by accident, and its
effect is to shadow the installed `alembic` distribution whenever the repo root
is on `sys.path` (which root `conftest.py` causes under pytest). Its fan-in of
49 in the coupling report is this shadowing, not real coupling: only **3**
distinct files import it.

Fix: delete `alembic/__init__.py`. The stock Alembic scaffold does not include
one.

### MEDIUM — `app/tasks/auto_apply.py` holds orchestration, policy, and persistence in one function
Evidence: `app/tasks/auto_apply.py:48` `apply_matched_jobs()` is 219 lines,
wrapping `_inner()` at `:57` which is 204 lines.

For context, this repo's own CLAUDE.md sets a 30-line function ceiling; 50
functions under `app/` exceed it, and this is the worst. The function decides
eligibility, enforces billing caps, drives the crawler, persists the
application, and emits notifications.

Fix: extract three named collaborators called in sequence —
`select_eligible_jobs(...)`, `enforce_apply_budget(...)`, and the existing
`application_service.apply_to_job(...)` — leaving the task as a thin
loop-and-log shell.

### MEDIUM — `application_service.py` mixes dispatch, persistence, and ML feedback
Evidence: `app/services/application_service.py:79-195` `apply_to_job()` is 117
lines; its own docstring enumerates five distinct responsibilities (fetch job,
acquire browser context, call crawler, persist application + status log, emit
ML feedback). Instability 0.587 at fan-in 19.

Fix: keep steps 1-3 in `apply_to_job`; move step 4 to
`application_repository.record_application(...)` and step 5 to
`ml.feedback.record_apply_signal(...)`.

---

## 3. Argument clumps

### MEDIUM — tenant/session clump and document clump in `apply_to_job`
Evidence: `app/services/application_service.py:79-87` — eight parameters,
including `schema_name`, `tenant_db`, `shared_db` (one clump: the tenant
execution context) and `resume_path`, `cover_letter` (a second: the application
documents).

Fix: introduce `TenantContext(schema_name, tenant_db, shared_db)` and
`ApplicationDocuments(resume_path, cover_letter)`. Signature becomes
`apply_to_job(user_id, job_id, ctx, docs, job_record=None)`.

### MEDIUM — matched-job descriptor clump in `queue_for_hitl`
Evidence: `app/services/application_service.py:238-247` — `portal`,
`portal_job_id`, `job_title`, `company`, `match_score` travel together and are
written straight onto one `JobApplication`.

Fix: pass the existing matched-job record (or a `MatchedJobRef` dataclass)
instead of five loose scalars. This also removes the field-by-field copy at
`:248-258`.

---

## 4. Cycles

None. The graph reports 0 strongly-connected components across 136 files, which
is genuinely good and worth preserving — the layering (`routers → services →
crawlers/ml → models`) is intact.

---

## 5. Coupling balance (Khononov)

**Volatility signal is unavailable from churn here, and I am not guessing it.**
The repository has 12 commits total and nearly every file shows 1 commit
(squashed phase commits), so `git log` carries no discriminating churn signal.
I therefore classified volatility from the subdomain grouping in
`specs/design/CONTEXT.md`: matching/applying = core, taxonomy/notifications/
billing = supporting, encryption/audit/database/anti-detection = generic.

Applying `BALANCE = (STRENGTH XOR DISTANCE) OR NOT VOLATILITY`:

| Relationship | Strength | Distance | Volatility | Balanced? |
|---|---|---|---|---|
| `application_service` → crawlers (`:60-76`) | functional | medium | high (core) | Yes — distance is medium, not far |
| `routers/*` → `database.get_tenant_db` (`app/database.py:34`) | model | medium | low (generic) | Yes — low volatility |
| `*` → `security/audit_log.audit` (`:9`) | contract | medium | low (generic) | Yes — narrow contract |
| crawlers → `anti_detection` (`:37-79`) | functional | near | low (generic) | Yes |

**No `coupling-imbalance` finding.** Nothing in this codebase is
high-strength + far-distance + high-volatility: it is a single deployable, so no
relationship is genuinely `far`. Flagging any of the above would violate the
rule's own discipline.

---

## Confirmed legitimate hubs

These carry high fan-in for correct reasons and should **not** be re-litigated
as god modules:

- `app/security/audit_log.py` — 33 lines, one `audit()` function, instability 0.
  Cross-cutting audit is *supposed* to have the highest fan-in in a
  compliance-bearing system (24 distinct importers).
- `app/database.py` — 48 lines; engine + session factories only.
- `app/crawlers/anti_detection.py` — 79 lines of stateless helpers; 8 importers.
- `app/crawlers/base.py` — the ABC and its DTOs (`RawJob`, `ApplicationReceipt`).
- `app/config.py`, `app/models/user.py`, `app/tenant_models/profile.py`,
  `app/tenant_models/application.py` — settings and ORM model modules.

### Ranking caveat for future readers

`coupling-report.md` fan-in counts import **edges**, not distinct importing
files, which inflates the hub ranking. `app/billing/gates.py` shows fan-in 33
but has only **2** distinct importers; `app/ml/matcher.py` shows 32 with **3**;
`alembic/__init__.py` shows 49 with **3**. Only `audit_log.py` (24) and
`database.py` (25) are hubs by importer count. Do not schedule refactoring off
the raw fan-in column.
