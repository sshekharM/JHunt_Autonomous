# Code Review (merged adversarial)

Policy: **union** · pass: **true** · BLOCK 0 / WARN 0 / INFO 20

### CR-A-001 — undefined
File: app/routers/auth.py:169
Axis: n/a · confidence: n/a

CHG-006 AC6's replay guard is unreachable in production. totp_last_used_step is written only by record_success (app/services/totp_lockout.py:36), which is immediately followed by user.totp_verified = True in the same transaction (auth.py:175 -> 192 -> 193). The only caller of _check_totp_code is /api/auth/totp/verify, and _pending_2fa_user (auth.py:153) raises 401 for any user with totp_verified True. Nothing in app/ ever sets totp_verified back to False and there is no admin TOTP verify endpoint, so is_replayed_step can only ever observe last=None and always returns False. The AC6 test (tests/unit/test_auth.py::test_a_code_from_the_last_accepted_step_is_a_replay) fabricates totp_verified=False + totp_last_used_step set, a row state the application cannot produce.

**Fix:** Keep the guard (it is the right shape for the future returning-user TOTP check) but record the reachability in one comment on app/services/totp_lockout.py::is_replayed_step: the step is only observable once TOTP is required at login, so today it is defence-in-depth, not a live control. Do not let the story claim the endpoint is replay-proof today without that note.

### CR-A-002 — undefined
File: app/routers/auth.py:168
Axis: n/a · confidence: n/a

Blank-secret contract mismatch between the migration and the app. alembic/versions/0004_encrypt_totp_secret.py maps "" <-> b"" deliberately, but app.security.encryption.decrypt(b"") raises cryptography.fernet.InvalidToken. Both production decrypt call sites (auth.py:168 in _check_totp_code and auth.py:127 in _totp_setup_response) would therefore raise an unhandled 500 for an anonymised row, which app/compliance/deletion.py:86 now sets to b"". Refuted as a BLOCK: anonymise keeps totp_verified True (so _pending_2fa_user 401s first) and rewrites email_hash to anonymised_<id> (so the callback lookup cannot find the row), and get_current_user already refuses is_active False. Reachable only if a future change clears totp_verified or adds another lookup path.

**Fix:** Minimum change: in _pending_2fa_user, refuse a row with a falsy totp_secret_encrypted (and a falsy is_active) with 401 before any decrypt, so the blank-secret sentinel can never reach Fernet.

### CR-A-003 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:86
Axis: n/a · confidence: n/a

The contract step (batch_alter_table -> SET NOT NULL + DROP COLUMN) has never been executed against the real users/admin_users definitions on any engine. tests/unit/test_0004_encrypt_totp_secret.py builds a 3-column SQLite stand-in (id, totp_secret, is_active) with no indexes, unique constraints or enum columns, so the SQLite batch-recreate path is proven only on a table that does not resemble the real one; tests/unit/test_0003_align_shared_schema_with_models.py mocks op entirely and stubs the row fetch to empty, so no SQL runs; and tests/integration/test_totp_secret_migration.py is RUN_DB_TESTS=1-only and was not run (disclosed in the context pack). The 0001..0005 chain has therefore never run end-to-end on PostgreSQL, and the first real deploy is the first execution. Not a BLOCK: on PostgreSQL alembic batch mode emits in-place ALTERs rather than a table rebuild, the change is inside one transaction so a failure aborts cleanly, and the user accepted the single-release expand+contract with no production data.

**Fix:** Run tests/integration/test_totp_secret_migration.py with RUN_DB_TESTS=1 against a throwaway PostgreSQL (docker compose up -d db) before merge, and extend it to upgrade to head (0005) and back rather than stopping at 0004.

### CR-A-004 — undefined
File: app/security/totp.py:30
Axis: n/a · confidence: n/a

verify_totp is now dead production code: the diff replaced its only production caller (app/routers/auth.py, previously `if not verify_totp(...)`) with matched_totp_step. Nothing under app/ imports it any more; the sole remaining reference is the harness in tests/validation/test_full_validation.py:136. Two overlapping code-verification paths now exist (pyotp.verify(valid_window=1) vs the hand-rolled -1/0/+1 loop with strings_equal). They agree on the window today, so a future change to one silently diverges from what the endpoint actually enforces.

**Fix:** Delete verify_totp from app/security/totp.py and point tests/validation/test_full_validation.py at matched_totp_step (truthiness of the returned step), so there is one definition of 'this code is valid now'.

### CR-A-005 — undefined
File: app/routers/auth.py:172
Axis: n/a · confidence: n/a

The failure that creates the lock writes only auth.totp_failed. auth.totp_locked is written on subsequent attempts (auth.py:163), so if the attacker stops after the fifth bad code nothing in the audit log records that the account was locked for 15 minutes; an operator sees five failures and no lock event. AC3 does not require it, and tests/unit/test_auth.py::test_fifth_failure_locks_the_account_and_later_attempts_get_429 pins the current sequence, so this is an observability gap rather than an AC miss.

**Fix:** Have record_failure return whether it locked and emit auth.totp_locked from that branch in addition to auth.totp_failed.

### CR-A-006 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:51
Axis: n/a · confidence: n/a

The None branches of encrypt_secret/decrypt_secret are unreachable: totp_secret is NOT NULL from 0001 onward and 0004 makes totp_secret_encrypted NOT NULL, so no row can be NULL in either direction, and if one were, the following SET NOT NULL would abort the migration anyway. tests/unit/test_0004_encrypt_totp_secret.py::test_blank_and_null_secrets_stay_blank_both_ways is the only thing exercising them.

**Fix:** Either drop the None branches and the (None, None) parametrize case, or add a one-line comment that they are defensive against a future nullable source column.

### CR-A-007 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:70
Axis: n/a · confidence: n/a

rewrite_column returns the row count but no production caller reads it - _move discards the value. The return exists only so tests/unit/test_0004_encrypt_totp_secret.py::test_rewrite_column_visits_every_row_in_batches can assert count == 4, i.e. API surface added for a test.

**Fix:** Give it a production use (log the per-table count from _move so a deploy leaves evidence of how many rows were re-encrypted), or drop the return and assert on the rewritten rows only.

### CR-A-008 — undefined
File: tests/unit/test_totp_secret_at_rest.py:28
Axis: n/a · confidence: n/a

test_totp_secret_is_no_longer_a_known_pii_violation asserts two tuples are absent from a set the same diff hardcoded to set(). The assertion cannot fail even if someone re-adds ("users", "totp_secret") as a plaintext column, because the exemption list would then be re-populated with a different entry or the test's specific tuples re-added - either way the useful protection comes from tests/unit/test_pii_policy.py's reflective check, not this one.

**Fix:** Assert KNOWN_VIOLATIONS == set() so any new exemption fails the test, and keep the reflective check as the column-level guard.

### CR-A-009 — undefined
File: app/services/totp_lockout.py:14
Axis: n/a · confidence: n/a

lock_seconds_left compares user.totp_locked_until with a tz-aware now. Correct on the supported runtime (PostgreSQL timestamptz returns aware datetimes via asyncpg), but any engine that returns naive values for DateTime(timezone=True) - SQLite, which the repo already uses for migration unit tests - makes `until <= now` raise TypeError and turn a lockout check into a 500.

**Fix:** No change needed for PostgreSQL. If a SQLite dev/test mode is ever wired to the ORM, normalise first: `until = until.replace(tzinfo=timezone.utc) if until.tzinfo is None else until`.

### CR-A-010 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:78
Axis: n/a · confidence: n/a

Keyset paging starts at after = "" with `WHERE id > after`, so a row whose String(36) primary key is the empty string is never visited and keeps NULL in the new column; the subsequent SET NOT NULL then aborts the migration with a constraint error rather than a clear message. Implausible for uuid4 ids (and it fails safe, inside the transaction), but the sentinel silently excludes one legal key value.

**Fix:** Optional: page with `after: str | None = None` and omit the WHERE clause on the first iteration, or assert rewrite_column's returned count equals SELECT count(*) in _move so a skipped row is reported as such.

### CRB-001 — undefined
File: app/security/totp.py:30
Axis: maintainability · confidence: high

verify_totp is now dead production code. matched_totp_step replaced it at the only production call site (app/routers/auth.py); the sole remaining reference is tests/validation/test_full_validation.py:135. verify_totp is not step-aware, so it silently skips the CHG-006 replay guard: a future caller that reaches for the obvious-looking helper reintroduces the R17 replay hole the branch just closed.

**Fix:** Delete verify_totp and point tests/validation/test_full_validation.py at matched_totp_step, or keep it with an explicit docstring warning that it bypasses the replay guard and must not be used on the verify path.

### CRB-002 — undefined
File: app/routers/auth.py:158
Axis: maintainability · confidence: medium

_check_totp_code has an asymmetric commit contract that nothing states: the failure branch commits the counter itself (line 170), while the success branch (record_success at line 175, which sets totp_failed_attempts/totp_locked_until/totp_last_used_step) relies on the caller committing afterwards. A second caller that forgets the commit would drop the replay step and the counter reset with no test failing, since only verify_totp_code is exercised.

**Fix:** Say so in the docstring ('failures commit; the caller must commit on success so totp_verified and the step land in one transaction'), or return a flag and let verify_totp_code own both commits.

### CRB-003 — undefined
File: app/routers/auth.py:168
Axis: behaviour · confidence: low

Unexercised failure path: app.security.encryption.decrypt raises InvalidToken on the b"" that app/compliance/deletion.py:86 writes for an anonymised user, so decrypt(user.totp_secret_encrypted) in _check_totp_code (line 168) and in _totp_setup_response (line 127) would surface as a 500 from main.py's global Exception handler rather than a 4xx. Migration 0004 deliberately handles the blank case (decrypt_secret returns "" for b""); the application path does not. Today it is unreachable only by two incidental invariants: _anonymise rewrites email_hash so the callback lookup misses, and _pending_2fa_user rejects totp_verified users (anonymise requires a session, which requires verification). Neither invariant is pinned by a test.

**Fix:** Guard the verify path on a blank secret (treat b"" as 'no enrolment', 401/409, or check user.is_active in _pending_2fa_user) and add a test that an anonymised row cannot reach decrypt.

### CRB-004 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:88
Axis: behaviour · confidence: medium

The only executed proof of AC6/AC7 for a destructive column-drop migration is SQLite. On SQLite op.batch_alter_table recreates the table, so the unit test never exercises the PostgreSQL statements this migration actually emits (ALTER COLUMN ... SET NOT NULL, DROP COLUMN, bytea executemany with mixed b""/ciphertext/NULL values). tests/integration/test_totp_secret_migration.py is written for exactly this but has never been run (context pack: 'Not run: PostgreSQL migration round trip'). Residual risk, not a defect I can reproduce.

**Fix:** Run tests/integration/test_totp_secret_migration.py with RUN_DB_TESTS=1 in the CI integration job (or against a throwaway Postgres container) and record the result before this reaches an environment holding real rows.

### CRB-005 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:56
Axis: maintainability · confidence: high

The None branches of encrypt_secret/decrypt_secret are unreachable against the real schema: users.totp_secret and admin_users.totp_secret are NOT NULL from 0001 and neither 0002 nor 0003 relaxes that. test_blank_and_null_secrets_stay_blank_both_ways pins behaviour the schema cannot produce, and if a NULL ever did appear the subsequent SET NOT NULL would fail mid-migration rather than being handled.

**Fix:** Leave as defensive code, or drop the None branch and let the migration fail loudly on an unexpected NULL.

### CRB-006 — undefined
File: app/security/totp.py:36
Axis: maintainability · confidence: high

The 90-second acceptance window is now expressed twice in one file: valid_window=1 in verify_totp (line 33) and the literal (-1, 0, 1) tuple in matched_totp_step (line 39). If one is ever tuned the other will drift.

**Fix:** Hoist the window to a module constant (e.g. TOTP_WINDOW_STEPS = 1) and derive both from it — or moot it by removing verify_totp per CRB-001.

### CRB-007 — undefined
File: app/services/totp_lockout.py:27
Axis: maintainability · confidence: high

record_failure never clears an expired totp_locked_until; only record_success does. After a lock lapses the column keeps a past timestamp, so the row cannot be read as 'locked' vs 'was locked once' without comparing to now(). Behaviourally correct (lock_seconds_left treats past as unlocked) but makes the column ambiguous for support queries and future admin UI.

**Fix:** Set user.totp_locked_until = None on the first failure recorded after the lock has lapsed, or document that the column is a deadline, not a state flag.

### CRB-008 — undefined
File: app/config.py:89
Axis: maintainability · confidence: medium

totp_max_failures and totp_lockout_minutes have no lower bound. TOTP_MAX_FAILURES=0 locks an account on the very first bad code (record_failure increments to 1 and 1 >= 0), and a negative value does the same — a misconfiguration self-DoS. Consistent with the rest of Settings (jwt_expiry_hours is unconstrained too), so noted rather than blocked.

**Fix:** Constrain with Field(5, ge=1) / Field(15, ge=1) if the project starts validating settings.

### CRB-009 — undefined
File: tests/integration/test_totp_secret_migration.py:35
Axis: maintainability · confidence: high

_alembic and the create_async_engine/dispose helper duplicate tests/integration/test_shared_migrations.py:25 and :50 near-verbatim. Trivial glue, but it is the second copy and a third is likely with the next migration.

**Fix:** Move _alembic and the engine helper into a shared integration conftest fixture and import it in both modules.

### CRB-010 — undefined
File: alembic/versions/0004_encrypt_totp_secret.py:12
Axis: maintainability · confidence: medium

The docstring's 'keyset-paged in batches of BATCH_SIZE' can be read as lock relief, but every batch runs inside the migration's single transaction and is followed by SET NOT NULL, which takes ACCESS EXCLUSIVE over the whole table. The batching bounds result-set memory only.

**Fix:** Reword to 'bounded result sets (one transaction; the table is exclusively locked for the whole migration)' so a future operator does not assume an online migration.

