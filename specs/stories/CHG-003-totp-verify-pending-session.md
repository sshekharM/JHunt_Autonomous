# CHG-003 — Bind TOTP verification to a pending-2FA session (risk R17)

## Problem

`POST /api/auth/totp/verify` (`app/routers/auth.py`) takes `user_id` and `code`
as query parameters and needs no prior authentication. On a valid code it marks
the account 2FA-verified and issues an eight-hour `access_token` session. So
anyone who has a user id and a matching TOTP code gets a full session without
the OAuth login. The OAuth callback returns a JSON body with the user id, which
makes this worse (`specs/brownfield/risk-map.md` R17).

## Acceptance criteria

1. When the OAuth callback takes the `totp_setup` branch (the user has not
   verified TOTP yet), it sets a `pending_2fa` cookie. The cookie is a signed
   JWT made with the `app.services.auth_service` helpers, with `sub=<user.id>`,
   `purpose="totp_setup"`, and a 10-minute expiry. It is `HttpOnly`, `Secure`,
   `SameSite=Lax`, has `Max-Age=600`, and is scoped to `/api/auth/totp`.
   The callback does not set an `access_token` cookie on this branch.
2. `POST /api/auth/totp/verify` takes only `code`. A `user_id` query parameter is
   ignored. The user comes from the `pending_2fa` cookie only.
3. The verify endpoint returns 401 and does not look up any user when the
   `pending_2fa` cookie:
   - is missing,
   - is expired or has a bad signature,
   - has a `purpose` other than `totp_setup`, or
   - is a normal `access_token` JWT, which has no `purpose` claim.
4. When the pending token and code are both valid, the endpoint:
   - sets `totp_verified = True` and commits,
   - issues the usual `access_token` cookie,
   - clears the `pending_2fa` cookie on the same path, and
   - returns the same `{"ok": true, "redirect": ...}` body as before.
5. An invalid code still returns 400 and writes the `auth.totp_failed` audit
   event. A success still writes `auth.totp_verified`. The endpoint keeps its
   `10/minute` rate limit.
6. A `pending_2fa` token cannot be used as a session. `get_current_user`
   returns 401 for any JWT that has a `purpose` claim.
7. Users who have already verified TOTP log in the same way as before: the
   OAuth callback redirects them with an `access_token` cookie.
8. A pending token can be used only once. When its user already has
   `totp_verified = True`, the verify endpoint returns 401 and issues no
   session. This was added from review findings SEC-R17-01 and CRB-004.
   `get_current_admin` also refuses tokens that have a `purpose` claim
   (review finding CRB-001).

## Out of scope

- **Whether every login should require a TOTP code is still a product
  decision.** Today, a user who has verified TOTP once is never asked for a
  code again. OAuth alone gets them a session. This change does not alter that
  policy. It only closes the unauthenticated path to the verify endpoint.
- Rotating or hiding the TOTP secret and QR code in the callback response
  (SEC-004 in `specs/reviews/security-review.md`).
- Frontend changes. The repo has no web frontend: no HTML or JS is tracked, and
  nothing calls `/totp/verify`. Any future client must send only `code` and
  rely on the browser sending the `pending_2fa` cookie.

## Implementation Status

Status: COMPLETE
Implemented: 2026-09-24 (branch `fix/auth-bypass`, commits aa9274d and the
review follow-up)
Files changed: app/services/auth_service.py, app/routers/auth.py,
app/dependencies.py
Tests added: tests/unit/test_auth.py, tests/unit/test_auth_service.py,
tests/unit/test_dependencies.py
AC coverage:
  - AC1: test_callback_for_unverified_user_sets_a_short_lived_pending_cookie,
    test_pending_token_is_purpose_bound_and_lives_ten_minutes
  - AC2: test_verify_without_pending_cookie_is_401_even_with_a_user_id,
    test_verify_derives_the_user_from_the_cookie_not_a_user_id_param
  - AC3: test_verify_rejects_anything_but_a_valid_pending_token[*],
    test_pending_decode_refuses_everything_else_with_401[*]
  - AC4: test_verify_with_pending_token_and_good_code_opens_a_session
  - AC5: test_verify_with_bad_code_is_400_and_audited,
    test_verify_keeps_its_rate_limit_of_ten_per_minute
  - AC6: test_non_session_tokens_are_refused_before_lookup[*],
    test_session_decode_refuses_purpose_bound_or_subjectless_tokens[*]
  - AC7: test_callback_for_verified_user_still_logs_straight_in[*]
  - AC8: test_pending_token_cannot_be_replayed_once_totp_is_verified,
    test_non_admin_tokens_are_401_before_lookup[purpose-bound]

Follow-ups raised in review, not done here:
- `code` is a query parameter, so TOTP codes show up in access logs. Move it
  to a request body.
- TOTP attempts are rate-limited only per IP. There is no lockout per account
  and no cache of codes already used.
