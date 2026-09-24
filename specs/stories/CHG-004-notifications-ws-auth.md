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
