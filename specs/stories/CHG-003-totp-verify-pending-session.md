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
