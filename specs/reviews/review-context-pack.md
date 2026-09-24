# Review context pack — CHG-002 admin IP allowlist (risk R5)

Story: `specs/stories/CHG-002-admin-ip-allowlist.md` (AC1–AC5).
Risk entry: `specs/brownfield/risk-map.md` R5.
Branch: `fix/admin-ip-allowlist`. Review mode: **adversarial** (security boundary + 9 files).

## Changed files
- `app/security/ip_allowlist.py`: `require_server_ip` now fails closed. It denies when the request has no client address or the IP is not listed, and the docstring states the empty-list and proxy behaviour.
- `app/config.py`: `allowed_ip_list` drops blank entries, so empty `ALLOWED_IPS` becomes `[]` (deny all) instead of `[""]`.
- `app/routers/admin/{config,crawls,ops,portals,taxonomy,users}.py`: `APIRouter(..., dependencies=[Depends(require_server_ip)])`.
- `.env.example`: `ALLOWED_IPS` is documented (exact match, empty = fail closed, Docker/nginx client-IP caveat).
- `tests/unit/test_ip_allowlist.py`: new acceptance/unit tests.

## Bug fixed in passing (AC5)
Before this change, empty `ALLOWED_IPS` gave `[""]`, and `request.client is None` gave `client_ip = ""`. That request matched and was allowed.

## Known deployment consequence (documented, out of scope)
`docker-compose.prod.yml` runs uvicorn behind nginx without `--forwarded-allow-ips`. So `request.client.host` is the nginx container IP, and with the default `ALLOWED_IPS=127.0.0.1` all admin access in prod is blocked (403) until operators configure it. This is fail-closed by design.

## Acceptance-test readability
Reviewers: judge whether `tests/unit/test_ip_allowlist.py` reads as the requirement (module docstring gives Given/When/Then; each test is tagged with its AC).

## Commands that passed
- `.venv/Scripts/python.exe -m pytest -q tests/unit/test_ip_allowlist.py`: 12 passed (8 were red before the fix)
- `.venv/Scripts/python.exe -m pytest -q`: 386 passed, 10 skipped
- `node .claude/scripts/run-gate-checks.js --only local-regression`: ok
- ruff / mypy: **not run**. They are not installed in `.venv` and the network is unavailable.
