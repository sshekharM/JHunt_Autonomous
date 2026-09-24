# Security Review — jhunt-autonomous — 2026-09-24

- **Branch:** `fix/admin-ip-allowlist`
- **Range:** `7c1cc13..9e364c2` (CHG-002; risk-map R5, R6, R9, R11, R16)
- **Scope:** changed production files plus immediate data-flow neighbours —
  `app/main.py`, `app/dependencies.py`, `app/routers/auth.py`, `app/database.py`,
  `app/security/encryption.py`, `app/security/audit_log.py`, `app/compliance/dpdpa.py`,
  `app/models/**`, `app/tenant_models/**`, `nginx/nginx.conf`, `Dockerfile`,
  `docker-compose.windows.yml`, and the pinned `uvicorn 0.29.0` proxy-headers middleware.

## Summary
- BLOCK findings: 0
- WARN findings: 4
- INFO findings: 7
- **Overall verdict: WARN** — gate **PASSES** (no critical/high finding)

## BLOCK Findings

None. Every candidate BLOCK was refuted with a concrete mitigation; see
"Adversarial verification" below for the evidence.

## WARN Findings

### [SEC-001] Unsanitised `X-Forwarded-For` on the nginx `/ws/` location
File: `nginx/nginx.conf` line 67 (trust created by `docker-compose.prod.yml` line 73)
Severity: medium (WARN)
Description: The diff makes uvicorn trust forwarded headers from nginx
(`--proxy-headers --forwarded-allow-ips 172.28.0.10`). The `/api/` location
rewrites `X-Forwarded-For` safely, but the `/ws/` location sets only `Upgrade`,
`Connection` and `Host`. nginx `proxy_set_header` directives are not inherited
from a sibling location, and there is no server-level default, so a client's own
`X-Forwarded-For` header is passed through verbatim on that path. Because the
connection reaches uvicorn from the trusted proxy address, uvicorn accepts that
header and `request.client.host` becomes fully attacker-chosen for anything
served under `/ws/`. There is no exploit today — no WebSocket route is
registered in `app/main.py`, and `/api/admin/*` cannot be reached through the
`/ws/` prefix (nginx normalises the URI before location matching, and Starlette
does not resolve `..` segments) — but the diff created the trust relationship
that turns this into a client-IP spoof the moment any route is added there.
Fix: Set `proxy_set_header X-Forwarded-For $remote_addr;` (and
`X-Real-IP $remote_addr`, `X-Forwarded-Proto $scheme`) in the `/ws/` location,
and prefer overwriting rather than appending in `/api/` as well so correctness
does not depend on uvicorn's rightmost-untrusted parsing.

### [SEC-002] The `172.28.0.10` proxy trust anchor is not reserved against dynamic allocation
File: `docker-compose.prod.yml` line 136
Severity: medium (WARN)
Description: The new `networks.default.ipam` block declares subnet
`172.28.0.0/24` and pins nginx to `172.28.0.10`, but sets no `ip_range`. Docker's
allocator assigns dynamic addresses from the same pool and only avoids addresses
that are allocated *at that moment*, so `db`, `redis`, `minio`, `app`, `worker`,
`beat` — or a scaled/added service — can take `172.28.0.10` before nginx's
endpoint is created. Two outcomes follow: nginx fails to start ("address already
in use"), or nginx comes up on a different address while another container holds
the address uvicorn trusts for forwarded headers. Neither outcome is remotely
exploitable (both leave the admin allowlist denying everyone, i.e. fail-closed,
and an internal container still needs an admin session to reach `/api/admin`),
but a security-critical trust anchor should not depend on container start order.
Fix: Constrain the dynamic pool so the static address is outside it, e.g. add
`ip_range: 172.28.0.128/25` beside the subnet, or put nginx and app on a
dedicated network. Assert the property at deploy time rather than assuming it.

### [SEC-003] R6 PII gate under-detects; several plaintext personal-data columns pass it
File: `app/security/pii_policy.py` line 46
Severity: medium (WARN)
Description: `PII_NAME_TOKENS` omits several high-signal tokens — `token`,
`key`, `name` (outside the `full_name` special case), `ssn`, `passport`, `url`,
`filename`, `history` — and the token set is not derived from the
`ENCRYPTED_FIELDS` list in the same module, so the two halves of the policy can
drift (`work_history_salary` is declared ENCRYPTED but would not be flagged if
stored plaintext). Concrete columns in the current schema hold personal data in
plaintext and pass the gate: `profile.work_history` and `profile.education`
(employers, institutions, dates — `app/tenant_models/profile.py` lines 61-62),
`profile.avatar_url` (line 66), and `master_resume.original_filename`
(`app/tenant_models/resume.py` line 15, commonly the candidate's own name).
Separately, `_is_protected` (line 63) is purely name-based: a column named
`*_encrypted` or `*_hash` that in fact stores plaintext passes unchallenged. The
test docstring claims "every mapped column ... that marks it as personal data",
which overstates the assurance actually provided.
Fix: Derive the token set from `ENCRYPTED_FIELDS`, add the missing tokens with a
small non-PII allowlist for `skill_name`/`field_name`/`schema_name`, and add a
complementary check that every `*_encrypted` column is a binary/`LargeBinary`
type written through `app.security.encryption.encrypt`.

### [SEC-004] Plaintext TOTP seeds accepted as a known violation
File: `app/security/pii_policy.py` line 57 (columns: `app/models/user.py` line 50, `app/models/admin.py` line 33)
Severity: medium (WARN)
Description: `KNOWN_VIOLATIONS` records `users.totp_secret` and
`admin_users.totp_secret` as plaintext. Listing them so they cannot spread is the
right ratchet, but the underlying weakness is live: anyone with read access to
the shared schema — a database backup, a SQL-injection foothold, a compromised
worker container — can generate valid second-factor codes for every user and
every admin, which defeats 2FA outright. Paired with SEC-009 this is a complete
authentication bypass for any account whose id is known.
Fix: Encrypt `totp_secret` at rest with the existing Fernet helper
(`totp_secret_encrypted`), migrate existing rows, and remove both entries from
`KNOWN_VIOLATIONS` so the test enforces the fix. Track as a dedicated ticket —
this should not stay "known" indefinitely.

## INFO Findings

### [SEC-005] No admin authentication endpoint exists; the AC1 test keys on the path prefix
File: `app/dependencies.py` line 35
Severity: low (INFO)
Description: `get_current_admin` requires an `admin_sub` JWT claim, and no route
in `app/routers/` issues a token containing it — there is no admin login path at
all, so the admin API is currently unreachable rather than under-protected (fail
closed). The forward-looking risk is in the ratchet: `test_ip_allowlist.py` line
45 enumerates only routes whose path starts with `/api/admin`, so a future admin
login route mounted under `/api/auth/admin/...` would silently escape both the
allowlist and the test that is supposed to guarantee coverage.
Fix: When the admin login route is added, mount it under `/api/admin` (or attach
`require_server_ip` explicitly) and broaden the coverage test to enumerate routes
by their dependency on `get_current_admin`/`require_role`, not by path prefix.

### [SEC-006] No perimeter restriction on `/api/admin/` at nginx
File: `nginx/nginx.conf` line 58
Severity: low (INFO)
Description: The single `location /api/` block proxies the entire API tree,
including `/api/admin/*`, from the public internet. The application-level exact-IP
match is the only layer protecting the admin plane; it is correctly implemented,
but a single control on a high-value surface.
Fix: Add a dedicated `location /api/admin/ { allow <admin-ip>; deny all;
proxy_pass http://api; ... }` block ahead of the generic `/api/` block, so the
perimeter enforces the policy independently of the application.

### [SEC-007] IPv6 and IPv4-mapped addresses are matched as literal strings
File: `app/security/ip_allowlist.py` line 24 (parser: `app/config.py` line 91)
Severity: low (INFO)
Description: The allowlist is an exact string comparison with no normalisation
and no CIDR support, so `::ffff:203.0.113.9` does not match `203.0.113.9` and
differently-compressed IPv6 literals do not match each other. Every mismatch
denies rather than admits, so the failure mode is safe, and `.env.example` lines
82-83 document it. The residual risk is operational: an admin on a dynamic or
IPv6 address is pushed toward a risky workaround (listing the proxy address or
setting `FORWARDED_ALLOW_IPS=*`), both of which `.env.example` now warns against.
Fix: Parse entries with `ipaddress.ip_network(..., strict=False)` and compare
with `ip_address(client) in network`, which normalises IPv4-mapped forms and adds
CIDR support without weakening the fail-closed default.

### [SEC-008] No `.dockerignore`; `COPY . .` can bake `.env` into the published image
File: `Dockerfile` line 38
Severity: low (INFO — pre-existing, untouched by this diff)
Description: The repository has no `.dockerignore` and the image is built with
`COPY . .`. A `.env` present in the build context — the same file
`docker-compose.prod.yml` line 56 loads — is copied into a layer of the published
`${APP_IMAGE}`, carrying `FERNET_KEY`, `APP_SECRET_KEY`, the Postgres and MinIO
credentials, every OAuth client secret and the system portal passwords. The local
`.venv/` is copied too. Reported as adjacent risk because it would nullify the
secret hygiene this change set documents in `.env.example`.
Fix: Add a `.dockerignore` covering `.env*`, `.venv/`, `.git/`, `specs/`,
`tests/`, `__pycache__/`, and rotate any secret that has already shipped in an
image.

### [SEC-009] Unauthenticated TOTP verification endpoint accepts an arbitrary `user_id`
File: `app/routers/auth.py` line 126
Severity: low (INFO — pre-existing, untouched by this diff)
Description: `POST /api/auth/totp/verify` takes `user_id` and `code` as query
parameters with no session requirement, sets `totp_verified = True` on success
and issues an eight-hour `access_token` cookie. It is rate-limited to 10/min, and
an attacker still needs a valid code, but the endpoint converts knowledge of a
TOTP seed (see SEC-004) plus a user id into a full session. It also permanently
marks the account 2FA-verified.
Fix: Bind the verification to the pending-login session established by the OAuth
callback rather than a caller-supplied `user_id`, move the parameters into a
request body, and use a constant-time comparison inside `verify_totp`.

### [SEC-010] Production healthcheck targets a path the application does not serve
File: `docker-compose.prod.yml` line 77
Severity: low (INFO — pre-existing, untouched by this diff)
Description: The app healthcheck probes `http://localhost:8000/health`, but the
route registered in `app/main.py` line 80 is `/api/health`. The container is
therefore reported unhealthy forever, which suppresses the signal an operator
would rely on to notice that the newly IP-restricted admin plane is misbehaving.
Fix: Point the healthcheck at `/api/health`.

### [SEC-011] Trailing-slash redirects disclose admin route existence before the IP check
File: `app/main.py` line 72
Severity: low (INFO)
Description: Starlette resolves trailing-slash redirects in the router, before
route dependencies are solved. A non-allowlisted client requesting
`/api/admin/users` receives `307` pointing at `/api/admin/users/` rather than the
intended `403`, confirming the route exists. The redirected request is then
correctly refused, so this is information disclosure only.
Fix: Set `redirect_slashes=False` on the admin routers, or register both path
forms explicitly, so unlisted IPs see a uniform `403`.

## Adversarial verification (candidate BLOCKs and why each was refuted)

**A. `X-Forwarded-For` spoofing bypasses the admin allowlist — REFUTED.**
nginx sends `X-Forwarded-For: <client-supplied values>, $remote_addr`
(`$proxy_add_x_forwarded_for`, `nginx/nginx.conf` line 62), appending the real
TCP peer last. The pinned `uvicorn==0.29.0`
(`.venv/Lib/site-packages/uvicorn/middleware/proxy_headers.py` lines 31-39) picks
the **rightmost** entry that is not in `trusted_hosts`; `trusted_hosts` is the
single literal `172.28.0.10` and `always_trust` is false because no configuration
in the repo sets `*` (verified across `.env.example`, both compose files and
`installer/core/env_writer.py` line 113). Attacker-injected entries therefore sit
to the left of the real address and are always ignored. If every entry were
trusted the middleware returns `None`, and `require_server_ip`
(`app/security/ip_allowlist.py` line 24) rejects a falsy host — fail closed. The
app container publishes no ports in `docker-compose.prod.yml`, so the only
external path is through nginx.

**B. Admin entry points outside `/api/admin` — REFUTED.**
`app/main.py` lines 72-77 register exactly six admin routers, all with the
`/api/admin` prefix and all carrying `dependencies=[Depends(require_server_ip)]`;
every endpoint in them also carries `require_role`. No non-admin router
references `AdminRole`, `require_role` or `get_current_admin`. There is no admin
login path to bypass (see SEC-005).

**C. IP check runs after authentication — REFUTED.**
Router-level dependencies are solved before the endpoint's own dependencies, so
`require_server_ip` raises `403` before `get_current_admin` reads a cookie. This
is asserted directly by `tests/unit/test_ip_allowlist.py` lines 69-73 against the
real ASGI app, in a suite that passes (454 passed).

**D. Empty / whitespace `ALLOWED_IPS` fails open — REFUTED.**
`app/config.py` line 93 drops blank entries, so `""`, `"   "` and `" , ,"` all
yield `[]`, and line 24 of the allowlist denies when the list is empty or the
client host is falsy. Covered by parametrised tests at lines 97-115.

**E. `APP_ENV` is not fail-safe — REFUTED.**
`app_env: Literal["development", "production"] = "production"` means an unset
value is production, and any other value raises `ValidationError` while
`app/config.py` is imported, so the process refuses to start rather than
degrading to a non-production posture. `is_production` gates the OpenAPI docs and
the `https_only` session cookie (`app/main.py` lines 42-53).
`docker-compose.prod.yml` line 63 pins `APP_ENV: production` in `environment:`,
which takes precedence over `env_file`, so a stale `.env` copied from
`.env.example` cannot downgrade a production stack.

**F. The consent audit event leaks PII — REFUTED.**
`app/compliance/consent_store.py` lines 45-50 log only `consent_version`, two
booleans and `llm_choice`, keyed by the pseudonymous `user_id` UUID. `ip_address`
and `user_agent` remain parameters of `record_consent` and are written only to
the `consent_records` row, matching the inline comment and R11.

**G. Tenant schema-name injection via the refactored onboarding path — REFUTED.**
The R16 refactor is behaviour-preserving (the old `__module__ and (...)` tuple
trick evaluated to the same pair). `schema_name` is `u_<sha256 hex[:32]>` and
every SQL interpolation of it passes `validate_schema_name`, which fullmatches
`u_[0-9a-f]{32}` (`app/database.py` lines 11-18, 80, 87, 104-106).
