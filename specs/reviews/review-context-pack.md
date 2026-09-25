# Review Context Pack — /change feat/totp-and-consent

- **Branch:** feat/totp-and-consent (cut from fix/auth-bypass)
- **Range:** `e483f81..HEAD`
- **Stories:** CHG-005 (`specs/stories/CHG-005-encrypt-totp-secret.md`, closes SEC-004 / R6 known violations); CHG-006 (`specs/stories/CHG-006-totp-account-lockout.md`, R17 follow-up)

## Commits
| SHA | Summary |
|-----|---------|
| 156e62c | test(deletion): pin which user-row PII fields anonymise blanks |
| 2735afe | feat(security): encrypt the TOTP secret at rest (CHG-005) |
| 160b4f0 | feat(auth): lock TOTP verify per account and refuse replayed codes (CHG-006) |

## Acceptance criteria (summary — story files are authoritative)
- CHG-005: `users`/`admin_users` store the TOTP seed only as `totp_secret_encrypted` (LargeBinary, NOT NULL, Fernet via `app.security.encryption`). `KNOWN_VIOLATIONS` is empty. Callback creates encrypted secrets and builds the URI/QR from the decrypted one; verify decrypts; anonymise sets `b""`. Migration 0004 (down 0003): add column, encrypt rows in keyset batches with `settings.fernet_key`, NOT NULL, drop plaintext; `""` <-> `b""`; downgrade decrypts back exactly. Single-release expand+contract was explicitly accepted by the user because the downgrade is lossless and there is no production data.
- CHG-006: after `totp_max_failures` (5) consecutive bad codes the account is locked `totp_lockout_minutes` (15). Locked -> 429 + Retry-After, no code check, no counter change, audit `auth.totp_locked`. Failure -> 400, `auth.totp_failed`, counter committed; the failure that hits the limit sets the lock and resets the count. Success resets count/lock and stores the matched time step; a step <= last accepted is a replay (400, counts as failure). User row read `FOR UPDATE`. Migration 0005 (down 0004) adds `totp_failed_attempts` int NOT NULL default 0, `totp_locked_until` timestamptz null, `totp_last_used_step` bigint null.
- Policy (user decision 2026-09-25): returning, already-verified users are NOT asked for TOTP at login. Do not flag this as a defect; it is recorded in CHG-003 and risk-map R17.

## Changed production files
- `app/models/user.py`, `app/models/admin.py` — column rename to `totp_secret_encrypted`; lockout columns on `User`
- `app/security/pii_policy.py` — `KNOWN_VIOLATIONS` emptied
- `app/routers/auth.py` — encrypt/decrypt secret; `_pending_2fa_user` uses `with_for_update()`; new `_check_totp_code`
- `app/compliance/deletion.py` — anonymise blanks `totp_secret_encrypted`
- `app/security/totp.py` — new `matched_totp_step`
- `app/services/totp_lockout.py` — new: `lock_seconds_left`, `is_replayed_step`, `record_failure`, `record_success`
- `app/config.py` — `totp_max_failures`, `totp_lockout_minutes`
- `alembic/versions/0004_encrypt_totp_secret.py`, `alembic/versions/0005_totp_lockout.py` — new

## Changed tests
`tests/unit/test_totp_secret_at_rest.py`, `tests/unit/test_0004_encrypt_totp_secret.py`, `tests/unit/test_0005_totp_lockout.py`, `tests/unit/test_totp_lockout.py` (new); `tests/unit/test_totp.py`, `tests/unit/test_auth.py`, `tests/unit/test_deletion.py`, `tests/unit/test_0003_align_shared_schema_with_models.py` (chain replay now includes 0004/0005 and batch ops), `tests/validation/test_full_validation.py`; `tests/integration/test_totp_secret_migration.py` (new, RUN_DB_TESTS=1 only).

## Frontend
None in repo; no client calls `/totp/verify`.

## Verification (all passed)
- `node .claude/scripts/run-compact.js --kind test -- .venv/Scripts/python.exe -m pytest -q` -> 571 passed, 11 skipped (baseline before branch work: 527 passed, 10 skipped)
- `.venv/Scripts/ruff.exe check .` -> 526 (baseline 526); `.venv/Scripts/mypy.exe app/` -> 59 (baseline 59)
- mutation-smoke: 0004 migration 13/13 killed; totp_lockout.py + totp.py + 0005 + routers/auth.py 44/44 killed
- `node .claude/scripts/run-gate-checks.js --only local-regression` -> ok
- Not run: PostgreSQL migration round trip (no PostgreSQL/Docker on the dev machine). Reversibility proven on SQLite in unit tests only.

## Review mode
adversarial (security boundary; 24 files, ~1000 lines). Reviewers read this pack, `git diff e483f81..HEAD`, and the touched files only.

## Review outcome
- code-reviewer A: PASS (0 BLOCK, 4 WARN, 6 INFO). code-reviewer B: PASS (0 BLOCK, 4 WARN, 6 INFO). Merged with `--policy union`: pass, 0 BLOCK.
- security-reviewer: PASS (0 BLOCK, 3 WARN, 7 INFO).
- Fixed in 3389d77: populate_existing on the FOR UPDATE lookup (SEC-006-01); 401 for a blank (anonymised) secret (CR-A-002/CRB-003); commit contract documented (CRB-002); KNOWN_VIOLATIONS asserted empty (CR-A-008); 0004 operational notes (SEC-005-01/02/04, CRB-010); replay guard noted as defence in depth (CR-A-001).
- Fixed in 9f6492c + ef56f77: dead `verify_totp` removed (CR-A-004/CRB-001/SEC-006-06).
- Open: PostgreSQL round trip of 0004/0005 not run (CR-A-003/CRB-004), because PostgreSQL/Docker was not available. Run `RUN_DB_TESTS=1` integration tests before any environment with real rows. MultiFernet key rotation (SEC-005-02) is not implemented. No `auth.totp_locked` event is written when the lock starts (CR-A-005). Settings have no `ge=1` bound (CRB-008).
- After fixes: 572 passed, 11 skipped; ruff 526 / mypy 59 (unchanged from baseline).
