# PR walkthrough

Generated: 2026-09-24T05:18:17.848Z
Files changed: **30**

## Intent

# Review Context Pack — /gate fix/admin-ip-allowlist - **Branch:** fix/admin-ip-allowlist - **Range:** `7c1cc13..9e364c2` (commits ca539f1..9e364c2) - **Story/risks:** CHG-002 (`specs/stories/CHG-002-admin-ip-allowlist.md`), risk-map items R5, R6, R9, R11, R16 (`specs/brownfield/risk-map.md`) ## Commits | SHA | Summary | |-----|---------| | ca539f1 | fix(security): enforce ALLOWED_IPS on every adm

## Logical change groups

_Ordered for review top-to-bottom (entry → domain → services → data → adapters → tests). Not alphabetical._

### 6. Config & infrastructure

- `.env.example`
- `app/config.py`
- `app/routers/admin/config.py`
  - ⚪ **INFO** (high): Router-level allowlist dependency duplicated in six files.
- `docker-compose.prod.yml`
  - 🟠 **WARN** (high): The nginx trust IP is a magic constant duplicated across two compose keys with no check that they agree.
  - ⚪ **INFO** (medium): Static ipv4_address 172.28.0.10 sits inside the dynamic allocation pool.
- `docker-compose.yml`
  - 🟠 **WARN** (medium): Compose fallback ${APP_ENV:-development} can silently override a production env_file value on the installer's deployment path.

### 7. Tests

- `tests/unit/test_admin_config_ops.py`
- `tests/unit/test_config.py`
  - ⚪ **INFO** (high): Rejection test does not assert which field failed validation.
- `tests/unit/test_consent_store.py`
- `tests/unit/test_ip_allowlist.py`
- `tests/unit/test_onboarding.py`
  - ⚪ **INFO** (medium): Characterization test asserts internal statement count.
- `tests/unit/test_pii_policy.py`

### 8. Docs & specs

- `specs/reviews/adversarial-review-audit.json`
- `specs/reviews/code-review-verdict-a.json`
- `specs/reviews/code-review-verdict-b.json`
- `specs/reviews/code-review-verdict.json`
- `specs/reviews/code-review.md`
- `specs/reviews/gate-checks.json`
- `specs/reviews/local-regression-gate-verdict.json`
- `specs/reviews/review-context-pack.md`
- `specs/reviews/security-review-verdict.json`
- `specs/stories/CHG-002-admin-ip-allowlist.md`

### 9. Other

- `app/compliance/consent_store.py`
- `app/routers/admin/crawls.py`
- `app/routers/admin/ops.py`
- `app/routers/admin/portals.py`
- `app/routers/admin/taxonomy.py`
- `app/routers/admin/users.py`
- `app/routers/onboarding.py`
  - ⚪ **INFO** (high): perf-smell PERF-N1-LOOP-QUERY findings on onboarding.py are false positives on pre-existing lines.
- `app/security/ip_allowlist.py`
  - ⚪ **INFO** (high): Denied admin attempts are not audited.
- `app/security/pii_policy.py`
  - 🟠 **WARN** (medium): consent_records.user_agent escapes the PII policy while the sibling ip_address needs a reviewed exception.
  - 🟠 **WARN** (medium): PII token list misses token/otp/ssn/passport and date_of_birth, so those columns would pass the R6 gate in plaintext.

## High-signal findings

- 🟠 **WARN** `app/security/pii_policy.py`: consent_records.user_agent escapes the PII policy while the sibling ip_address needs a reviewed exception.
- 🟠 **WARN** `app/security/pii_policy.py`: PII token list misses token/otp/ssn/passport and date_of_birth, so those columns would pass the R6 gate in plaintext.
- 🟠 **WARN** `docker-compose.prod.yml`: The nginx trust IP is a magic constant duplicated across two compose keys with no check that they agree.
- 🟠 **WARN** `docker-compose.yml`: Compose fallback ${APP_ENV:-development} can silently override a production env_file value on the installer's deployment path.

## Blast radius (from code-graph)

**Likely callers of changed code:**
- `alembic/env.py`
- `app/crawlers/glassdoor.py`
- `app/crawlers/indeed.py`
- `app/crawlers/linkedin.py`
- `app/crawlers/monster.py`
- `app/crawlers/naukri.py`
- `app/crawlers/session_manager.py`
- `app/crawlers/shine.py`
- `app/database.py`
- `app/llm/anthropic_client.py`
- `app/llm/ollama_client.py`
- `app/main.py`
- `app/notifications/discord_bot.py`
- `app/notifications/email_client.py`
- `app/notifications/telegram_bot.py`
- `app/security/encryption.py`
- `app/security/totp.py`
- `app/services/auth_service.py`
- `app/services/resume_service.py`
- `app/services/storage_service.py`

**Modules this change depends on:**
- `datetime`
- `hashlib`
- `sqlalchemy.ext.asyncio`
- `app/compliance/dpdpa.py`
- `pydantic_settings`
- `pydantic`
- `typing`
- `fastapi`
- `app/models/admin.py`
- `app/dependencies.py`
- `app/security/audit_log.py`
- `app/tasks/crawl_jobs.py`
- `sqlalchemy`
- `app/database.py`
- `app/models/user.py`
- `app/models/portal_account.py`
- `app/tenant_models/profile.py`
- `app/tenant_models/skill.py`
- `app/tenant_models/resume.py`
- `app/security/encryption.py`

## 5-minute human review script

1. Read **Intent** and confirm the PR matches the story/AC.
2. Walk **Logical change groups** top to bottom — skip alphabetical GitHub view.
3. Open every 🔴 BLOCK and 🟠 WARN; dismiss only with evidence.
4. Spot-check one happy path and one failure path in tests (group 7).
5. Confirm `specs/reviews/quality-card.md` is PASS and wiki links are fresh.
6. Merge only if you understand the change groups — not because CI is green alone.
