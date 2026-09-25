# Evaluator Report — /gate fix/admin-ip-allowlist (instance 1, canonical)

- **Range:** `7c1cc13..9e364c2`
- **Mode:** test-backed static. Docker is unavailable on this host, so no runtime,
  no Playwright, no live HTTP evaluation was possible. Every criterion below is
  judged from the diff plus **executed** tests; anything that can only be proven
  by running the stack is marked `UNVERIFIED-runtime`, never PASS.
- **Date:** 2026-09-24

## Overall verdict: **PASS (with 1 UNVERIFIED-runtime item)**

No acceptance criterion failed. Five of six are PASS with executed test evidence.
One (prod forwarded-allow-ips end to end) cannot be proven without Docker and must
be verified on a Docker host before the prod deploy.

## Deterministic evidence

Targeted suite (executed, not inferred):

```
node .claude/scripts/run-compact.js --kind test -- .venv/Scripts/python.exe -m pytest -q \
  tests/unit/test_ip_allowlist.py tests/unit/test_config.py tests/unit/test_pii_policy.py \
  tests/unit/test_consent_store.py tests/unit/test_onboarding.py tests/unit/test_admin_config_ops.py
=> exit 0, 80 passed, 1 warning
```

Full-suite result carried from the context pack: 454 passed, 10 skipped, exit 0.
Security gate: `specs/reviews/security-review-verdict.json` → `pass: true`, 0 BLOCK,
2 WARN (both about the forwarded-header topology, both addressed afterwards by
`ac46fda` — fixed nginx IP + explicit NEVER lines in `.env.example`).

## Per-criterion results

### R5 — admin IP allowlist enforced on every `/api/admin/*` route — **PASS**

Executed evidence, not inspection:
- `test_every_admin_route_depends_on_require_server_ip` walks `app.routes` and
  asserts `require_server_ip` is in the dependant chain of every `APIRoute` whose
  path starts with `/api/admin`. It enumerates routes instead of a fixed list, so
  a future admin router is covered automatically (AC1).
- `test_every_admin_endpoint_refuses_an_unlisted_ip` is parametrized over every
  registered admin endpoint and asserts 403.
- Ordering (IP check before auth) is proven by a *pair* of tests, which is the
  only way to prove it black-box: unlisted IP → 403 with the allowlist detail
  message; listed IP → 401 `"Not authenticated."`. If the IP check ran after auth
  the first would be 401.
- Fail-closed: `allowed_ip_list` now filters blanks (`if ip.strip()`), and
  `require_server_ip` rejects on `not client_ip` as well as non-membership.
  Covered by `test_empty_allowlist_parses_to_no_entries` (`""`, `"   "`, `" , ,"`),
  `test_empty_allowlist_denies_every_request` (hosts `127.0.0.1`, `""`, `None`),
  `test_request_without_client_address_is_denied`.
- Diff confirms all 6 admin routers registered in `app/main.py` (users, portals,
  crawls, taxonomy, config, ops) carry `dependencies=[Depends(require_server_ip)]`
  at router level. Grep confirms no `/api/admin` path is declared anywhere outside
  `app/routers/admin/`.

Minor (non-blocking) note: the AC1 test filters `isinstance(r, APIRoute)`, so an
admin **WebSocket** route would not be checked. There is no admin websocket today
(the only one is `/ws/{user_id}` in `notifications.py`), so this is future-proofing,
not a present gap.

### R9 — `APP_ENV` secure by default — **PASS**

- `app_env: Literal["development","production"] = "production"`.
- `test_unset_app_env_defaults_to_production` (asserts both `app_env` and the
  derived `is_production`), `test_development_is_an_explicit_opt_in`, and
  `test_unrecognised_app_env_is_rejected` parametrized over
  `prod|Production|dev|""` expecting `ValidationError` — so a typo fails fast
  instead of silently meaning "not production".
- Dev compose opts in explicitly: `APP_ENV: ${APP_ENV:-development}` on the `app`
  service.

WARN (non-blocking): the dev compose `worker` and `beat` services did **not** get
the same explicit `APP_ENV` override. They rely on `env_file: .env`. If a developer's
`.env` omits `APP_ENV`, the app container runs development while worker/beat run
production — an inconsistency, though it fails in the safe direction.

### R6 — no plaintext PII column can be added — **PASS**

- `unprotected_pii_columns()` is a real policy function, and
  `test_no_model_column_stores_pii_in_plaintext` reflects over **actual SQLAlchemy
  metadata** for both `Base` and `TenantBase` (importing every module in
  `app.models` and `app.tenant_models` plus `app.compliance.dpdpa`), so adding a
  plain `phone` column breaks the build. This is enforcement, not documentation.
- The known violations (`users.totp_secret`, `admin_users.totp_secret`) are pinned
  two ways: new violations fail `test_no_model_column_stores_pii_in_plaintext`, and
  `test_known_violations_still_exist` fails if a fixed entry is left stale in the
  list. Both directions of the ratchet are covered.
- The reviewed exception (`consent_records.ip_address`) is table-scoped, proven by
  `test_reviewed_plaintext_exception_passes_only_for_its_table`.

Minor note: `_looks_like_pii` is a token-set heuristic. Column names like `ssn`,
`passport_number`, `resume_text`, or an unsplit `emailaddress` would not be flagged.
The heuristic is the policy's weak edge, not a defect in this change.

### R11 — `record_consent` emits `consent.granted` without network identifiers — **PASS**

- `test_record_consent_writes_a_grant_audit_entry` asserts the exact event name
  and the exact `details` payload (version, both consent booleans, llm_choice).
- `test_audit_entry_carries_no_network_identifiers` asserts the literal IP
  `203.0.113.7` and UA `UA/1.0` appear nowhere in the audit kwargs — the negative
  assertion the criterion actually requires.
- `test_record_consent_persists_exact_consents` confirms the record itself still
  keeps IP/UA and the consent-text hash, so the audit change did not weaken the
  legally load-bearing record. Audit fires after `commit()`, so an audit failure
  cannot lose a consent grant.

### Prod — uvicorn trusts `X-Forwarded-For` only from nginx at 172.28.0.10 — **UNVERIFIED-runtime**

Not a failure; simply unprovable here. There is **zero test coverage** for this
(grep for `forwarded|172.28|proxy-headers` in `tests/` returns nothing), and it is
a deployment-topology change whose only real proof is a running stack.

Static findings that support it but do not substitute for runtime proof:
- `docker-compose.prod.yml` runs `--proxy-headers --forwarded-allow-ips 172.28.0.10`
  and pins nginx to `ipv4_address: 172.28.0.10` via a `networks.default` ipam block
  with subnet `172.28.0.0/24`.
- `nginx/nginx.conf:62` sets `X-Forwarded-For $proxy_add_x_forwarded_for`, which
  **appends** nginx's `$remote_addr` last; installed uvicorn is 0.29.0, whose
  proxy-headers middleware resolves the rightmost untrusted entry. So a
  client-supplied XFF cannot win — provided the trusted host is the specific nginx
  address and never `*`. `.env.example` now says exactly that, in NEVER form.

Must be confirmed on a Docker host before prod: (a) the custom subnet does not
collide and nginx actually receives 172.28.0.10; (b) an admin request through nginx
resolves `request.client.host` to the real client IP; (c) a spoofed
`X-Forwarded-For: <allowed-ip>` from an outside client still gets 403.

Known open follow-up (from the story, still open): nginx has no
`location /api/admin/ { allow ...; deny all; }` perimeter block, and denied admin
attempts are not written to the audit log.

### R16 — behavior-preserving refactor of thumbprint/schema derivation — **PASS**

The strongest structural evidence in this branch:
- `70e723f` adds `tests/unit/test_onboarding.py` (+334 lines) and **touches no
  production file**.
- `9e364c2` changes **only** `app/routers/onboarding.py` (2 insertions, 4 deletions)
  and **touches no test file** (`git diff 70e723f..9e364c2 -- tests/` is empty).
  So the pin genuinely preceded the refactor and was not adjusted to fit it.
- The removed expression `schema_name_from_thumbprint.__module__ and (...)` relied
  on a truthy `__module__` string to return the tuple and called
  `generate_thumbprint` twice. `generate_thumbprint` is pure
  (`sha256_hash(f"{email.lower().strip()}:{phone.strip()}")`), so collapsing to a
  single call plus a plain assignment is semantically identical.
- Behavior pinned by `test_step1_sets_identity_from_email_and_phone`,
  `test_step1_returns_full_response_body` (exact response payload),
  `test_step1_rejects_duplicate_identity`, and
  `test_step1_duplicate_check_query_predicates` (compiled SQL asserts both the
  thumbprint equality and the `id != self` exclusion).

## Registry gate cross-check

`run-gate-checks.js` reported a **perf-smell BLOCK** — 5x `PERF-N1-LOOP-QUERY` in
`app/routers/onboarding.py` (147/169/259/277/306). I verified this independently
rather than taking the context pack's word:

- All five are `async for tenant_db in get_tenant_db(user.schema_name):`.
- `app/database.py:90-96` shows `get_tenant_db` is a **single-yield async generator**
  (`async with tenant_session(...): yield session`), i.e. a dependency/context
  helper, not an iteration over rows. The body executes exactly once.
- All five lines are **pre-existing**; this diff touched only lines 94-100 of that
  file.

Verdict on the BLOCK: **false positive**, does not gate this change. The 2 WARNs
(unbounded load in admin ops/portals) are likewise pre-existing.

## Layers not executed

| Layer | Status | Reason |
|---|---|---|
| API (live HTTP) | NOT RUN | Docker unavailable; no running app |
| Playwright / browser | NOT RUN | Docker unavailable; no frontend served |
| Accessibility (axe) | NOT RUN | requires a rendered page |
| Performance ratchet / SLO | NOT RUN | requires a running app + `/metrics` |
| Schema/design | NOT RUN | no runtime surface to compare |
| ruff / mypy | NOT RUN | not installed in `.venv` |

Backend behaviour was instead verified through FastAPI `TestClient`, which
exercises the real ASGI app, real routers, and real dependency chain in-process —
the closest available substitute for Layer 1, and genuine evidence for R5's
403-before-401 ordering.

## features.json

`features.json` is `[]` — no entry matches CHG-002 or R5/R6/R9/R11/R16, so no
update was made (per the rule: only modify a matching entry).

## Source changes

None. This evaluation modified no source file.
