# Code Review — fix/admin-ip-allowlist (`7c1cc13..9e364c2`)

**Verdict: PASS** — 0 BLOCK, 4 WARN, 6 INFO.
Reviewed cold against the changed production files and tests named in
`specs/reviews/review-context-pack.md`, plus every file the diff calls into or is called from.

## What was verified (not just read)

| Check | Result |
|---|---|
| Full suite, `APP_ENV` unset (the new production default) | `pytest -q tests/` → exit 0, **454 passed, 10 skipped** |
| The six touched test files | 80 passed |
| PII heuristic executed over every mapped column in `app/models` + `app/tenant_models` + `app.compliance.dpdpa` | flags exactly `(users, totp_secret)` and `(admin_users, totp_secret)` — matches `KNOWN_VIOLATIONS`, no unlisted violation |
| uvicorn 0.29.0 `ProxyHeadersMiddleware` source in `.venv` | `get_trusted_client_host` walks the XFF list right-to-left and returns the first untrusted host; nginx uses `$proxy_add_x_forwarded_for`, so the rightmost entry is the real peer → **not spoofable** |
| `ruff` / `mypy` | not installed in `.venv` — NOT RUN |

### R5 — admin IP allowlist
All six admin routers carry `dependencies=[Depends(require_server_ip)]`; `require_server_ip` had
**zero importers** at `7c1cc13` (confirmed with `git grep` at the base commit), so this is the wiring
R5 asked for and not a duplicate control. Router-level dependencies solve before the path operation's
own dependencies, and `test_admin_route_from_unlisted_ip_is_forbidden_before_auth` executes that
ordering (403, not 401). `test_every_admin_route_depends_on_require_server_ip` enumerates the app's
live routes, so a future admin router cannot silently skip the guard. No admin-capable endpoint
exists outside the `/api/admin` prefix (`grep` over `app/routers/`). The fail-closed changes are
coherent: `allowed_ip_list` now drops blanks so `ALLOWED_IPS=""` yields `[]`, and `require_server_ip`
rejects a falsy `client_ip` — which also covers the `scope["client"] = (None, 0)` case uvicorn
produces when every XFF entry is trusted. `require_server_ip` is the only consumer of
`allowed_ip_list`, so the `[""]`→`[]` contract change breaks no caller.

### R9 — `APP_ENV` Literal + production default
Consumers checked: `app/main.py:42-43` (docs), `:52-55` (`https_only`), `app/database.py:27`
(`echo`), `app/routers/admin/config.py:27` (reported value), `installer/core/env_writer.py:55`
(writes `production`), `tests/unit/test_database.py:119`. All tolerate the `Literal`; auth cookies
were already `secure=True` unconditionally (`app/routers/auth.py:118,150`) and `SessionMiddleware`'s
session is not used anywhere in `app/`, so the flip has no hidden behavioural blast radius. The suite
passes with `APP_ENV` unset, which is the honest proof. See **CR-004** for the compose-side fallback.

### R6 — PII policy
Heuristic executed, not inferred. `_is_protected` is name-based by design (a column named
`*_encrypted` is trusted to be encrypted) — acceptable for a policy gate. `column in HASHED_FIELDS`
is redundant with the `_hash` suffix test for both current members, harmless. Gaps in **CR-001**,
**CR-002**.

### R11 — consent audit
`audit()` is called after `db.commit()`, so no event is emitted for a failed write. The `details`
keys do not collide with `logger.bind`'s reserved keys (`event`, `timestamp`, `user_id`, `admin_id`,
`resource`). `record_consent`'s signature is unchanged; its single caller
(`app/routers/onboarding.py:310`) is unaffected. `test_audit_entry_carries_no_network_identifiers`
would genuinely fail if IP or UA leaked into the payload.

### Prod networking
`--proxy-headers --forwarded-allow-ips 172.28.0.10` with nginx pinned at that address is correct,
and the folded-scalar `command:` still yields a valid argv. `location /api/` sets
`X-Forwarded-For`/`-Proto`; `location /ws/` does not, so websocket clients still appear as the proxy
— no admin route is a websocket, so this is inert. Findings **CR-003**, **CR-005**.

### R16 — onboarding refactor
Behaviour-preserving, confirmed by reading both helpers: `generate_thumbprint` is a pure
`sha256(email.lower().strip() + ":" + phone.strip())` and `schema_name_from_thumbprint` a pure
f-string, so the removed `schema_name_from_thumbprint.__module__ and (...)` truthiness no-op and the
duplicate `generate_thumbprint` call were both side-effect-free. The pinning tests landed in the
preceding commit (`70e723f`) and assert the derived values, the response body, the provisioned
schema, and the 409 branch. File shrank 326 → 324 lines, so the length ratchet moves the right way.

## Findings

| ID | Level | Conf | Axis | Location |
|----|-------|------|------|----------|
| CR-001 | WARN | medium | behaviour | `app/security/pii_policy.py:46` |
| CR-002 | WARN | medium | behaviour | `app/security/pii_policy.py:45` |
| CR-003 | WARN | high | maintainability | `docker-compose.prod.yml:75,134` |
| CR-004 | WARN | medium | behaviour | `docker-compose.yml:68` |
| CR-005 | INFO | medium | behaviour | `docker-compose.prod.yml:134` |
| CR-006 | INFO | high | maintainability | `app/routers/admin/config.py:9` (+5 siblings) |
| CR-007 | INFO | high | behaviour | `app/security/ip_allowlist.py:24` |
| CR-008 | INFO | high | maintainability | `tests/unit/test_config.py:28` |
| CR-009 | INFO | medium | maintainability | `tests/unit/test_onboarding.py:169` |
| CR-010 | INFO | high | behaviour | `app/routers/onboarding.py:147` (perf-smell triage) |

### CR-001 — WARN — `consent_records.user_agent` escapes the PII policy
`app/security/pii_policy.py:46`. `ip_address` in `consent_records` needs an explicit reviewed
exception, but `user_agent` in the same row is simply never flagged — `_looks_like_pii` has no
`agent` token. The comment this range adds to `record_consent` treats the two identically ("IP and
user agent stay in the consent record only, not the log stream"), so the policy encodes half of its
own stated model.
**Fix:** add `"agent"` to `PII_NAME_TOKENS` and `("consent_records", "user_agent")` to
`PLAINTEXT_EXCEPTIONS` with the same DPDPA-evidence rationale.

### CR-002 — WARN — token list misses the secrets most likely to arrive next
`app/security/pii_policy.py:45`. `token`, `otp`, `ssn`, `passport` are absent, and `dob` only matches
as a standalone underscore token so `date_of_birth` slips through. A future plaintext
`telegram_bot_token` or `refresh_token` column would pass `test_no_model_column_stores_pii_in_plaintext`,
which is the entire R6 enforcement mechanism. No such column exists today (heuristic executed).
**Fix:** add `"token"`, `"otp"`, `"ssn"`, `"passport"`, `"birth"`. Do **not** add `"key"` — it would
false-positive on the existing `master_resume.minio_key` / `tailored_resumes.minio_key`.

### CR-003 — WARN — the nginx trust IP is an unchecked duplicated constant
`docker-compose.prod.yml:75` and `:134` (third prose copy in `.env.example`). `172.28.0.10` is the
trust anchor for the whole allowlist, written twice with nothing verifying they agree — CI runs
`nginx -t` only, never `docker compose config`. If either drifts, uvicorn stops trusting nginx and
every admin request is matched against nginx's own container IP: admin is locked out, or an operator
"fixes" it by adding the proxy address to `ALLOWED_IPS`, which is exactly the internet-wide exposure
`.env.example` warns about.
**Fix:** declare it once (`NGINX_IP=172.28.0.10` in `.env`) and interpolate
`${NGINX_IP:-172.28.0.10}` into both the `ipv4_address` and `--forwarded-allow-ips`.

### CR-004 — WARN — `${APP_ENV:-development}` fails open on a production path
`docker-compose.yml:68`. A compose `environment:` entry overrides `env_file:`, so the fallback — not
the `.env` value — decides whenever `APP_ENV` is not interpolable (non-default `--env-file`, explicit
`--project-directory`, missing `.env`). That re-enables `/api/docs` and non-https session cookies,
the exact posture R9 removed. It matters because `installer/core/autostart.py:49` deploys real
installations with **this** file while `installer/core/env_writer.py:55` writes `APP_ENV=production`.
The default installer paths (systemd `WorkingDirectory=install_dir`; the Windows task's
`cd /d install_dir`) resolve correctly today — hence WARN, not BLOCK.
**Fix:** `${APP_ENV:-production}`. Local dev still gets `development`, because `init.sh` copies
`.env.example` (which sets `APP_ENV=development`) and compose interpolates it.

### CR-005 — INFO — static `172.28.0.10` sits inside the dynamic IPAM pool
`docker-compose.prod.yml:134`. Docker allocates dynamic addresses sequentially from `.2` and does not
pre-reserve static ones. Six dynamically addressed services today top out near `.7`, so `.10` is
free; three more services (or a scaled replica) can claim `.10` first and nginx — which starts last
via `depends_on: app` — then fails with "Address already in use".
**Fix:** add `ip_range: 172.28.0.128/25` to the ipam config and move nginx into it (e.g.
`172.28.0.130`), so dynamic allocation can never collide with the pinned proxy.

### CR-006 — INFO — guarded-router construction duplicated six times
`app/routers/admin/{config,crawls,ops,portals,taxonomy,users}.py`. Contained by the route-enumerating
test, so this is style only. **Fix (optional):** pass `dependencies=[Depends(require_server_ip)]`
once per `app.include_router(admin_*)` call in `app/main.py`.

### CR-007 — INFO — denied admin attempts are not audited
`app/security/ip_allowlist.py:24`. An IP scan of `/api/admin` leaves no trace while successful admin
actions are audited. Already recorded as a deferred follow-up in the story.
**Fix:** `audit("admin.ip_denied", details={"client_ip": client_ip})` before raising.

### CR-008 — INFO — rejection test does not pin the failing field
`tests/unit/test_config.py:28`. Non-vacuous today only because the root `conftest.py` seeds the
required secrets. **Fix:** `pytest.raises(ValidationError, match="app_env")`.

### CR-009 — INFO — characterization test asserts statement count
`tests/unit/test_onboarding.py:169` (`len(wired.tenant.executed) == 2`). Deliberate pinning ahead of
the R15/R16 extraction; replace with an outcome assertion once that refactor lands.

### CR-010 — INFO — perf-smell BLOCK on `onboarding.py` is a false positive
`app/routers/onboarding.py:147,169,259,277,306`. `get_tenant_db` (`app/database.py:90-96`) is a
single-yield async generator, so `async for tenant_db in get_tenant_db(schema)` executes exactly one
iteration — the dependency-generator-as-context-manager idiom, not an N+1 loop. Exhausting the
generator runs its `finally`, so the session is closed and there is no leak. All five lines are
pre-existing and untouched by this range (the diff changed only lines 94-100).
**Fix:** no code change; suppress or teach the sensor this idiom.

## Out of scope / not re-litigated

- Pre-existing oversized functions and files (R15), the unvalidated-schema-name class (R7 — now
  guarded by `validate_schema_name` in `provision_user_schema`), and the `/health` vs `/api/health`
  healthcheck path in `docker-compose.prod.yml:77`: untouched by this diff.
- Security-boundary vulnerability hunting is the security-reviewer's lane; the proxy-trust analysis
  above is included only because it is load-bearing for the correctness of the allowlist wiring.
