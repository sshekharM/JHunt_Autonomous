# CHG-002 — Enforce the admin IP allowlist (risk R5)

## Problem

`app/config.py` defines `allowed_ips` / `allowed_ip_list` and
`app/security/ip_allowlist.py` defines `require_server_ip`, but nothing imports
the dependency. No `/api/admin/*` route checks the caller's IP, so `ALLOWED_IPS`
in `.env.example` suggests a control that does not exist
(`specs/brownfield/risk-map.md` R5).

The parser also has a fail-open edge case: an empty `ALLOWED_IPS` parses to
`[""]`, and a request with no client address (`request.client is None`) resolves
to `""`, so it would match and be allowed.

## Acceptance criteria

1. Every route whose path starts with `/api/admin` has `require_server_ip` in
   its dependency chain. This includes admin routers added later, because the
   test lists the app's routes instead of a fixed set.
2. A request to an admin route from an IP not in `ALLOWED_IPS` gets
   `403 Forbidden`. The IP check runs before authentication, so an
   unauthenticated caller from a disallowed IP gets 403, not 401.
3. A request from an IP in `ALLOWED_IPS` passes the IP check and goes on to the
   normal admin authentication and role checks.
4. `ALLOWED_IPS` is parsed as a comma-separated list. Whitespace around entries
   is stripped, and blank entries (such as from a trailing comma) are dropped.
5. An empty (or all-blank) `ALLOWED_IPS` fails closed: it denies every admin
   request. A request with no client address is always denied. This is stated
   in the `require_server_ip` docstring and in `.env.example`.

## Out of scope

- CIDR ranges and wildcard entries (exact IP match only).
- Reverse-proxy client-IP resolution (uvicorn `--forwarded-allow-ips`). This is
  documented as a deployment caveat, not changed here.
- IP restriction on non-admin routes.

## Implementation Status

Status: COMPLETE (uncommitted on `fix/admin-ip-allowlist`)
Implemented: 2026-09-24
Files changed: app/security/ip_allowlist.py, app/config.py,
  app/routers/admin/{config,crawls,ops,portals,taxonomy,users}.py, .env.example
Tests added/updated: tests/unit/test_ip_allowlist.py
AC coverage:
  - AC1: test_every_admin_route_depends_on_require_server_ip,
    test_every_admin_endpoint_refuses_an_unlisted_ip (11 routes)
  - AC2: test_admin_route_from_unlisted_ip_is_forbidden_before_auth
  - AC3: test_admin_route_from_listed_ip_proceeds_to_authentication, test_listed_ip_passes_the_check
  - AC4: test_allowlist_parsing_strips_whitespace_and_drops_blanks
  - AC5: test_empty_allowlist_parses_to_no_entries, test_empty_allowlist_denies_every_request,
    test_request_without_client_address_is_denied
Review: adversarial code review (2 instances, union) PASS, 0 BLOCK; security review PASS, 0 BLOCK.

Follow-ups (deferred WARNs):
  - Prod admin is unreachable behind nginx until uvicorn trusts nginx's forwarded headers
    (`--forwarded-allow-ips`) or nginx gets a `location /api/admin/ { allow ...; deny all; }` block.
  - Denied admin attempts are not written to the audit log (`app/security/audit_log.py`).
