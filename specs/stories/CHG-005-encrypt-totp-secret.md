# CHG-005 — Encrypt the TOTP secret at rest (PII policy R6)

## Problem

`users.totp_secret` and `admin_users.totp_secret` are stored in plaintext
(`String(64)`). Anyone who can read the database, a backup, or a replica can
generate valid 2FA codes for every account. The PII policy test
(`tests/unit/test_pii_policy.py`) lists both columns in
`app/security/pii_policy.py::KNOWN_VIOLATIONS`, waiting for this fix.

## Acceptance criteria

1. `users` and `admin_users` have no `totp_secret` column. They have a
   `totp_secret_encrypted` column (`LargeBinary`, NOT NULL) that holds the
   secret Fernet-encrypted with `app.security.encryption.encrypt`.
2. `KNOWN_VIOLATIONS` no longer lists either column, and the PII policy test
   passes by column name.
3. The OAuth callback creates new users with an encrypted secret. The
   `totp_setup` response still carries a provisioning URI and QR code built
   from the decrypted secret.
4. `POST /api/auth/totp/verify` checks the code against the decrypted secret.
   Behaviour is otherwise unchanged.
5. Anonymising a user blanks the secret (`totp_secret_encrypted = b""`).
6. Alembic migration `0004` (down_revision `0003`) adds the new column,
   encrypts every existing row in bounded batches with `FERNET_KEY` from app
   settings, makes the column NOT NULL, and drops the plaintext column. A blank
   secret (an anonymised user's `""`) becomes `b""`, not a ciphertext.
7. The downgrade decrypts back into a plaintext `totp_secret` column and drops
   the encrypted one, so `0003 → 0004 → 0003` returns the original values.

## Out of scope

- Rotating the Fernet key, or re-keying secrets.
- Hiding the TOTP secret/QR from the callback response (SEC-004).
- A separate expand/contract release: the user accepted a single reversible
  migration because the downgrade restores the plaintext exactly and there
  is no production data yet (see migration 0003's notes).

## Implementation Status

Status: COMPLETE
Implemented: 2026-09-25 (branch `feat/totp-and-consent`)
Files changed: app/models/user.py, app/models/admin.py,
app/security/pii_policy.py, app/routers/auth.py, app/compliance/deletion.py,
alembic/versions/0004_encrypt_totp_secret.py
Tests added/updated: tests/unit/test_totp_secret_at_rest.py,
tests/unit/test_0004_encrypt_totp_secret.py,
tests/integration/test_totp_secret_migration.py (RUN_DB_TESTS=1),
tests/unit/test_0003_align_shared_schema_with_models.py (chain now includes
0004 and replays batch ops), tests/unit/test_auth.py,
tests/unit/test_deletion.py, tests/validation/test_full_validation.py
AC coverage:
  - AC1: test_totp_secret_is_stored_only_encrypted[users|admin_users],
    test_head_has_exactly_the_model_tables_and_columns,
    test_head_nullability_and_primary_keys_match_models
  - AC2: test_totp_secret_is_no_longer_a_known_pii_violation,
    test_no_model_column_stores_pii_in_plaintext
  - AC3: test_callback_creates_an_unverified_user_on_first_login,
    test_callback_builds_the_provisioning_uri_from_the_decrypted_secret
  - AC4: test_verify_with_pending_token_and_good_code_opens_a_session,
    test_verify_with_bad_code_is_400_and_audited
  - AC5: test_anonymise_blanks_pii_on_the_user_row
  - AC6: test_encrypt_then_decrypt_round_trips_a_secret,
    test_blank_and_null_secrets_stay_blank_both_ways,
    test_the_migration_uses_the_app_fernet_key,
    test_rewrite_column_visits_every_row_in_batches,
    test_upgrade_encrypts_every_secret_and_drops_the_plaintext_column,
    test_0004_encrypts_secrets_and_downgrade_restores_them (PostgreSQL)
  - AC7: test_downgrade_restores_the_original_plaintext,
    test_0004_encrypts_secrets_and_downgrade_restores_them (PostgreSQL)

Reversibility: proven on SQLite in the unit suite (upgrade then downgrade
restores every value). The PostgreSQL round trip is written but was not run
here: no PostgreSQL or Docker was available on the dev machine.
