# Review Context Pack — /change fix/auth-bypass

- **Branch:** fix/auth-bypass
- **Range:** `53a8844..HEAD`
- **Stories/risks:** CHG-003 (`specs/stories/CHG-003-totp-verify-pending-session.md`) → risk R17; CHG-004 (`specs/stories/CHG-004-notifications-ws-auth.md`) → risk R18 (`specs/brownfield/risk-map.md`)

## Commits
| SHA | Summary |
|-----|---------|
| aa9274d | fix(auth): bind TOTP verify to a pending-2FA session (R17) |
| b02ef98 | fix(notifications): authenticate the notifications WebSocket (R18) |
| 7286234 | fix(auth): make pending-2FA tokens single-use and admin-proof (R17 review) |

## Acceptance criteria (summary — read the story files for the full list)
- R17: OAuth callback's `totp_setup` branch sets a signed `pending_2fa` cookie (JWT, `purpose=totp_setup`, `sub=user.id`, 10 min, HttpOnly/Secure/SameSite=Lax, path `/api/auth/totp`). `POST /api/auth/totp/verify` takes only `code`; user derived from that cookie; 401 if missing/expired/wrong-purpose/normal access token; clears pending cookie on success; rate limit (10/min) and audit events unchanged. `get_current_user` refuses any JWT with a `purpose` claim. Login policy for already-verified users is intentionally unchanged (pending product decision).
- R18: `/api/notifications/ws/{user_id}` reads `access_token` cookie before `accept()`; closes 1008 without accept/register if missing/invalid/purpose-bound/`sub != user_id`. Disconnect cleanup cannot raise on a missing registry entry; empty entries dropped. `push_to_user` logs failed sends instead of `except: pass`.

## Changed production files
- `app/services/auth_service.py` — new `create_pending_2fa_token`, `decode_pending_2fa_token`, `session_user_id`, `PENDING_2FA_*` constants
- `app/routers/auth.py` — callback `totp_setup` branch extracted to `_totp_setup_response` (sets pending cookie); `verify_totp_code` signature/auth change
- `app/dependencies.py` — `get_current_user` uses `session_user_id`
- `app/routers/notifications.py` — WS auth, `_session_user`, `_unregister`, push logging

## Changed tests
`tests/unit/test_auth.py`, `tests/unit/test_auth_service.py`, `tests/unit/test_dependencies.py`, `tests/unit/test_notifications.py` (all new; fakes only, no DB).

## Frontend
None in repo (no tracked HTML/JS; `installer/` is a desktop setup wizard that never calls these endpoints). No caller to update.

## Verification (all passed)
- `node .claude/scripts/run-compact.js --kind test -- .venv/Scripts/python.exe -m pytest -q` → 519+ passed, 10 skipped (baseline before change: 454 passed)
- `node .claude/scripts/mutation-smoke.js` on all four production files → 100% killed (auth trio 40/40, notifications 8/8); pre-commit gates passed on both commits
- `node .claude/scripts/run-gate-checks.js --only local-regression` → ok
- ruff / mypy: **not installed** in `.venv` or on PATH — not run

## Risk triggers
Authentication, session tokens/cookies, WebSocket auth, API route signature change (`/totp/verify` drops `user_id`).

## Reviewer notes
- Pending cookie is scoped to path `/api/auth/totp`; `delete_cookie` uses the same path/attrs.
- Pending token and session token share the signing key/algorithm; separation relies on the `purpose` claim (checked both directions).
- `callback` was already over the 30-line function cap (grandfathered); the change shrinks it.

## Review outcome
- Tier: adversarial (security boundary, 11 files, ~1000 lines).
- code-reviewer B: PASS (0 BLOCK, 2 WARN, 3 INFO) -> `code-review-verdict-b.json`.
- code-reviewer A: stopped by the user before writing a verdict; `code-review-verdict-a.json` is stale (previous gate) and was not merged. The union merge was not run.
- security-reviewer: PASS (0 BLOCK, 1 WARN, 9 INFO) -> `security-review-verdict.json`.
- Fixed in 7286234: SEC-R17-01/CRB-004 (a pending token is spent once the user is verified), CRB-001 (admin dependency refuses purpose-bound tokens), CRB-002 (unused import), CRB-005 (test for the user_id param).
- Final: 526 passed, 10 skipped; mutation-smoke 100% on all touched production files.
