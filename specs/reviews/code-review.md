# Code Review (merged adversarial)

Policy: **union** · pass: **true** · BLOCK 0 / WARN 3 / INFO 11

### CRA-001 — WARN
File: tests/unit/test_ip_allowlist.py:42
Axis: maintainability · confidence: medium



**Fix:** Keep the route enumeration, but assert behaviour: parametrize over the (method, path) pairs of every /api/admin APIRoute, call each with the default TestClient host absent from ALLOWED_IPS, and assert 403. Rename to test_every_admin_endpoint_refuses_an_unlisted_ip. (TestClient in starlette/fastapi 0.111 does not accept a client= kwarg, so keep using the 'testclient' host constant.)

### CRA-002 — WARN
File: app/security/ip_allowlist.py:24
Axis: behaviour · confidence: medium



**Fix:** Add one line to the .env.example Security block naming the IPv6 loopback forms ('::1', '::ffff:127.0.0.1') and advising listing them alongside 127.0.0.1; optionally add a test asserting an IPv6 host is denied unless listed. Do not add CIDR/normalisation logic - that is explicitly out of scope for CHG-002.

### CRA-003 — INFO
File: app/routers/admin/ops.py:13
Axis: maintainability · confidence: high



**Fix:** Optional: pass the dependency once at include time in app/main.py, or mount the six routers under a single parent APIRouter that carries the dependency. Acceptable as-is because the route-enumeration test fails closed on a forgotten router.

### CRA-004 — INFO
File: app/main.py:57
Axis: behaviour · confidence: medium



**Fix:** No change required for CHG-002; note it if the story ever grows a 'no admin surface visible off-allowlist' criterion.

### CRA-005 — INFO
File: .env.example:73
Axis: maintainability · confidence: medium



**Fix:** Reword to 'checked before admin authentication and role checks', or leave until an admin login route lands.

### CRA-006 — INFO
File: tests/unit/test_ip_allowlist.py:20
Axis: maintainability · confidence: high



**Fix:** Annotate: def _request(host: str | None) -> SimpleNamespace and def _depends_on(dependant: Dependant, target: Callable[..., object]) -> bool.

### CRA-007 — INFO
File: specs/reviews/review-context-pack.md:27
Axis: maintainability · confidence: high



**Fix:** Run ruff check . and mypy app/ before merge once the environment allows.

### CRB-001 — WARN
File: docker-compose.prod.yml:71
Axis: behaviour · confidence: high



**Fix:** Open a follow-up story to set FORWARDED_ALLOW_IPS/--forwarded-allow-ips to the nginx service address and resolve the client IP from X-Forwarded-For, or give nginx a fixed address on the compose network; until then add the lockout to the deploy runbook.

### CRB-003 — INFO
File: app/routers/admin/config.py:9
Axis: maintainability · confidence: high



**Fix:** Optional: mount the six routers under one parent APIRouter(prefix="/api/admin", dependencies=[Depends(require_server_ip)]) in app/main.py so the control is declared once.

### CRB-004 — INFO
File: tests/unit/test_ip_allowlist.py:59
Axis: behaviour · confidence: high



**Fix:** Add assert response.json()["detail"] == "Not authenticated." so the test pins that the 401 comes from admin authentication rather than any other guard.

### CRB-005 — INFO
File: tests/unit/test_ip_allowlist.py:31
Axis: maintainability · confidence: medium



**Fix:** Rename to `api_client` or add a one-line comment stating the shadowing is intentional.

### CRB-006 — INFO
File: tests/unit/test_ip_allowlist.py:65
Axis: maintainability · confidence: high



**Fix:** Add the # AC3 tag for consistency.

### CRB-008 — INFO
File: tests/unit/test_ip_allowlist.py:44
Axis: behaviour · confidence: high



**Fix:** None required.

### CRB-009 — INFO
File: specs/brownfield/risk-map.md:69
Axis: maintainability · confidence: high



**Fix:** Close or annotate R5 with the CHG-002 reference when the change merges.

