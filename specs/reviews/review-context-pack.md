# Review context pack — CHG-007 DPDPA consent withdrawal

Story: `specs/stories/CHG-007-consent-withdrawal.md` (acceptance criteria AC1–AC11).
Diff: `git diff ea5e664..HEAD` on branch `feat/totp-and-consent` (commits 4a522c4..a3dcee3).
Review tier: adversarial (19 files, ~1300 lines, crosses the data/API/persistence boundary).

## Changed production files
- `alembic/versions/0006_consent_withdrawal.py` — adds `consent_records.event` (NOT NULL, server default 'granted'), reversible.
- `app/compliance/dpdpa.py` — `ConsentRecord.event`.
- `app/compliance/consent_store.py` — `CONSENT_SCOPES`, `current_consent`, `consent_history`, `consent_allows` (fail closed), `withdraw_consent` (FOR UPDATE on users row, append-only, idempotent, audit `consent.withdrawn` with scopes only).
- `app/services/consent_service.py` — `withdraw()` orchestrates: record → disable tenant `auto_apply_enabled` → `execute_deletion(user, DeletionMode.soft_delete, db)` for data_processing.
- `app/schemas/consent.py`, `app/routers/consent.py` — `GET /api/consent`, `POST /api/consent/withdraw` (get_current_user), registered in `app/main.py`.
- `app/tasks/auto_apply.py` — `_consent_refused` gate: before tenant access (auto_apply) and before job loading when HITL is off (llm_processing); audit `consent.enforced`.
- Style-only commit 4a522c4 (ruff import sorting) and test-only commits (test_main.py, test_auto_apply_pins.py, integration test).

## Constraints
- `app/compliance/deletion.py` must NOT be changed (R12 irreversible data). Known pre-existing gap: soft delete does not set `users.scheduled_deletion_at` and no job purges after 30 days.
- Re-grant after withdrawal is out of scope.
- `screening_service.answer_screening_question` calls an LLM but has no caller; not gated.

## Tests (all passed)
- `node .claude/scripts/run-compact.js --kind test -- .venv/Scripts/python.exe -m pytest -q` → 635 passed, 11 skipped (baseline before change: 572 passed, 11 skipped).
- New: tests/unit/test_consent_withdrawal.py, test_consent.py (router, TestClient), test_consent_service.py, test_auto_apply.py, test_auto_apply_pins.py, test_main.py, test_dpdpa.py, test_0006_consent_withdrawal.py; chain test extended to 0006; tests/integration/test_consent_withdrawal_db.py (RUN_DB_TESTS only, not run here — no Docker/PostgreSQL).
- ruff: clean on new files; remaining findings in touched files are pre-existing (auto_apply.py BLE001 x3, DTZ011, F841).
- mypy: no errors in new modules (remaining are pre-existing, e.g. app/config.py call-arg).

## Reviewer instructions
Read only this pack, `git diff ea5e664..HEAD`, and the touched files. Check correctness of the consent semantics (append-only, idempotence, concurrency via FOR UPDATE, ordering by consented_at), enforcement completeness, API contract (422/409/401), and test quality.
