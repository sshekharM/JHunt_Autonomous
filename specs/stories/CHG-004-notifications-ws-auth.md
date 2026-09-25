# CHG-004 — Authenticate the notifications WebSocket (risk R18)

## Problem

`/api/notifications/ws/{user_id}` (`app/routers/notifications.py`) accepts any
connection for any `user_id`. It registers the socket in the in-memory
registry, so `push_to_user` then sends that user's real-time notifications to
whoever connected. The disconnect handler also does
`_connections[user_id].remove(websocket)`, which raises `KeyError` or
`ValueError` if the registry entry is already gone
(`specs/brownfield/risk-map.md` R18).

## Acceptance criteria

1. Before `accept()`, the endpoint reads the `access_token` cookie from the
   WebSocket handshake and decodes it with the session-token helpers
   (`decode_access_token` via `session_user_id`).
2. The endpoint closes the socket with code **1008 (policy violation)** when:
   - the cookie is missing,
   - the cookie is invalid or expired,
   - the token is purpose-bound, such as `pending_2fa`, or
   - the token's `sub` differs from the path `user_id`.

   In all of these cases it does not accept the socket and does not register
   it.
3. A valid session token whose `sub` equals the path `user_id` is accepted and
   registered. It gets the 30-second `{"type": "ping"}` keep-alive as before.
4. On disconnect, the endpoint removes only this socket from the registry.
   Other sockets for the same user stay registered, and an empty user entry is
   dropped. If the entry or the socket is already missing, cleanup does nothing
   and does not raise.
5. If a send to one of the user's sockets fails in `push_to_user`, the failure
   is logged as `notifications.ws_push_failed` and delivery to the user's
   other sockets continues. Before this change the error was dropped silently
   with `except Exception: pass`.

## Out of scope

- Checking on each connection that the user still exists and is active. The
  signed session token is trusted for its 8-hour lifetime.
- Origin checks for cross-site WebSocket hijacking. The `SameSite=Lax` session
  cookie is not sent on cross-site WebSocket handshakes. Browser support
  varies, so this is tracked, not changed here.
- Frontend changes. The repo has no web client that opens this socket. A
  same-origin client only has to let the browser send the `access_token`
  cookie.

## Implementation Status

Status: COMPLETE
Implemented: 2026-09-24 (branch `fix/auth-bypass`, commit b02ef98 and the
review follow-up)
Files changed: app/routers/notifications.py
Tests added: tests/unit/test_notifications.py
AC coverage:
  - AC1/AC2: test_unauthorised_handshake_is_closed_1008_unaccepted_and_unregistered[*],
    test_handshake_over_http_is_rejected_with_1008
  - AC3: test_authorised_socket_is_registered_pinged_then_removed
  - AC4: test_disconnect_keeps_the_users_other_sockets,
    test_disconnect_with_a_missing_registry_entry_does_not_raise[*]
  - AC5: test_push_logs_a_failed_socket_and_still_reaches_the_rest

Notes from review:
- The handler closes the socket before `accept()`. Under uvicorn, that makes
  the server reject the handshake with HTTP 403, so code 1008 never reaches a
  real client. Starlette's TestClient reports the close as 1008. Either way
  the connection is denied (CRB-003).
- The nginx config sets the upgrade headers only under `location /ws/`, but
  this route lives under `/api/`. So the WebSocket handshake probably cannot
  complete behind the shipped proxy, which means this control has not yet run
  in a proxied deployment. This is a pre-existing deployment gap, raised by
  the security review and not fixed here.
