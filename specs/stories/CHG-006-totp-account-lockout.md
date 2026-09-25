# CHG-006 — Per-account TOTP lockout and replay guard (R17 follow-up)

## Problem

`POST /api/auth/totp/verify` is limited only to 10 requests a minute per IP
(CHG-003). An attacker who holds a user's `pending_2fa` cookie and spreads
guesses over several IPs can keep guessing that user's 6-digit code. A code
that has already been accepted can also be sent again within its 90-second
window. Both were raised as follow-ups in the CHG-003 review.

## Acceptance criteria

1. After `settings.totp_max_failures` (default 5) failed codes in a row for one
   account, TOTP verification for that account is locked for
   `settings.totp_lockout_minutes` (default 15). The count is per account, not
   per IP, and is stored on the user row.
2. While the account is locked, the endpoint returns 429 with a `Retry-After`
   header. It does not check the code, does not change the counters, and writes
   the `auth.totp_locked` audit event.
3. A failed code returns 400, writes `auth.totp_failed`, and adds one to the
   stored count, which is committed. The lock starts on the failure that
   reaches the limit, and the count starts again from zero after it.
4. When the lock time has passed, codes are checked again.
5. A good code resets the count, clears the lock, and stores the time step it
   matched in `totp_last_used_step`.
6. A code whose time step is at or before `totp_last_used_step` is refused as
   a replay: 400, `auth.totp_failed`, and it counts as a failure.
7. The user row is read with `SELECT … FOR UPDATE`, so two requests at the same
   time for the same account cannot both use the count or the same code.
8. New columns on `users`: `totp_failed_attempts` (integer, NOT NULL,
   default 0), `totp_locked_until` (timestamptz, nullable) and
   `totp_last_used_step` (bigint, nullable). Migration `0005` (down_revision
   `0004`) adds them, and its downgrade removes them.

## Out of scope

- Asking returning users for a TOTP code at login. On 2026-09-25 the user
  decided that returning users are **not** asked for TOTP at login (see
  CHG-003). This change only hardens the enrolment verify step.
- Lockout for admin TOTP. There is no admin TOTP verify endpoint yet.
- Telling the user by email or notification that their account was locked.

## Implementation Status

Status: COMPLETE
Implemented: 2026-09-25 (branch `feat/totp-and-consent`)
Files changed: app/config.py, app/models/user.py, app/security/totp.py,
app/services/totp_lockout.py (new), app/routers/auth.py,
alembic/versions/0005_totp_lockout.py
Tests added/updated: tests/unit/test_totp_lockout.py, tests/unit/test_totp.py,
tests/unit/test_0005_totp_lockout.py, tests/unit/test_auth.py,
tests/unit/test_0003_align_shared_schema_with_models.py (chain now ends at 0005)
AC coverage:
  - AC1: test_fifth_failure_locks_the_account_and_later_attempts_get_429,
    test_the_failure_that_reaches_the_limit_locks_and_restarts_the_count,
    test_settings_default_to_five_failures_and_fifteen_minutes,
    test_limits_come_from_settings
  - AC2: test_a_locked_account_is_refused_without_checking_even_a_good_code,
    test_lock_seconds_left[*]
  - AC3: test_verify_with_bad_code_is_400_and_audited,
    test_failures_below_the_limit_only_count
  - AC4: test_codes_are_checked_again_once_the_lock_has_expired
  - AC5: test_success_resets_the_count_and_remembers_the_step,
    test_success_clears_the_count_and_the_lock_and_remembers_the_step,
    test_a_code_within_one_step_returns_the_step_it_was_made_for[*]
  - AC6: test_a_code_from_the_last_accepted_step_is_a_replay,
    test_a_step_at_or_before_the_last_accepted_one_is_a_replay[*]
  - AC7: test_verify_with_pending_token_and_good_code_opens_a_session
    (asserts the lookup ends in FOR UPDATE)
  - AC8: test_upgrade_adds_the_counters_and_existing_rows_start_at_zero,
    test_downgrade_removes_exactly_what_upgrade_added,
    test_head_has_exactly_the_model_tables_and_columns,
    test_head_nullability_and_primary_keys_match_models
