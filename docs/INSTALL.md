# Installing jH_ANS: step-by-step guide

jH_ANS is a FastAPI job-hunt automation service. It runs as a set of Docker containers:

| Service | What it does | Port (dev) |
|---|---|---|
| `app` | FastAPI API: auth, onboarding, applications, admin | 8000 |
| `worker` | Celery worker: crawling, matching, auto-apply, notifications | none |
| `beat` | Celery scheduler: periodic crawls, status checks, digests | none |
| `db` | PostgreSQL 16: shared tables plus one schema per user | 5432 |
| `redis` | Celery broker and result backend | 6379 |
| `minio` | S3-compatible storage for resumes | 9000 (API), 9001 (console) |
| `nginx` | TLS termination and reverse proxy (**production only**) | 80, 443 |

There are three ways to run it. Pick one:

- **A. Local / evaluation stack**: Docker Compose on your machine, with API docs enabled. [Go to A](#a-local--evaluation-stack-docker-compose)
- **B. Production stack**: Docker Compose behind nginx with TLS. [Go to B](#b-production-stack-docker-compose--nginx)
- **C. Developer setup without Docker**: Python virtualenv for running the tests. [Go to C](#c-developer-setup-without-docker-tests-only)

> The repository contains the API only; there is no web frontend in it yet. `FRONTEND_URL` is used only for CORS and redirects.

---

## 1. Prerequisites

| Need | For | Check |
|---|---|---|
| Git | all | `git --version` |
| Docker Engine 24+ with the Compose v2 plugin (or Docker Desktop) | A, B | `docker compose version` |
| OpenSSL | generating secrets, B's TLS certs | `openssl version` |
| Python 3.12 | C only | `python --version` |
| 4 CPU cores, 8 GB RAM, 20 GB disk | A, B (the worker runs headless Chromium) | none |

**Windows:** use Docker Desktop with the WSL2 backend in Linux-containers mode. If the host is itself a virtual machine, nested virtualization must be enabled on it. Docker Desktop needs a paid subscription at larger companies; check your licence.

## 2. Get the code

```bash
git clone https://github.com/sshekharM/JHunt_Autonomous.git
cd JHunt_Autonomous
git checkout claude/jh-ans-job-hunt-system-0airwv   # the default branch
```

## 3. Configure `.env`

```bash
cp .env.example .env
```

Open `.env` and set the values below. The app **refuses to start** if a required secret is missing.

### 3.1 Required secrets

Generate each with OpenSSL and paste it in:

| Variable | How to generate | Notes |
|---|---|---|
| `APP_SECRET_KEY` | `openssl rand -hex 32` | Signs session tokens. Changing it logs everyone out. |
| `FERNET_KEY` | `openssl rand -base64 32 \| tr '+/' '-_'` | Encrypts TOTP secrets, emails and portal credentials at rest. **Never change it once real data exists.** There's no re-encryption tool, so the data would become unreadable. Back it up. |
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` | Used by both the `db` container and the app |
| `MINIO_SECRET_KEY` | `openssl rand -hex 16` | Used by both the `minio` container and the app |

### 3.2 Application settings

| Variable | Set to |
|---|---|
| `APP_ENV` | `development` for A, `production` for B. Unset means production: API docs off and https-only cookies. Any other value fails at startup. |
| `APP_BASE_URL` | The URL users reach the API at, e.g. `http://localhost:8000` (A) or `https://jobs.example.com` (B) |
| `FRONTEND_URL` | Your frontend's origin (CORS). Leave the default if you have none. |
| `ALLOWED_IPS` | Comma-separated **exact** IPs allowed to call `/api/admin/*`. **An empty value blocks all admin access.** For A, from the Docker host, use the compose network gateway (usually `172.18.0.1`; see [Troubleshooting](#troubleshooting)). For B, use your admins' public IPs. |
| `JWT_EXPIRY_HOURS` | Session length. Defaults to `4`; leave it unless you mean to change it. |

### 3.3 Sign-in providers (at least one)

Users sign in with OAuth. Google, LinkedIn and Facebook are supported. The Microsoft keys in `.env.example` are **not used yet**.

For each provider you enable, create an OAuth app in its developer console and register this **redirect URI**:

```
<APP_BASE_URL>/api/auth/callback/<provider>        e.g. https://jobs.example.com/api/auth/callback/google
```

Then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, and the same pair for LinkedIn or Facebook.

On first sign-in, each user scans a QR code into an authenticator app. TOTP is checked at enrolment only; later sign-ins use OAuth and a session cookie.

### 3.4 Optional integrations

| Feature | Variables |
|---|---|
| LLM (resume tailoring, matching) | `ANTHROPIC_API_KEY` for Claude, or `OLLAMA_BASE_URL` + `OLLAMA_MODEL` for a self-hosted model. Users choose per account during onboarding. |
| Email notifications | `EMAIL_PROVIDER` (`smtp` or `sendgrid`) + `SMTP_*` or `SENDGRID_API_KEY`, and `EMAIL_FROM` |
| Telegram / Discord notifications | `TELEGRAM_BOT_TOKEN`; `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` |
| Job-portal crawling | `<PORTAL>_SYSTEM_EMAIL` / `<PORTAL>_SYSTEM_PASSWORD` for Naukri, LinkedIn, Glassdoor, Indeed. Check each portal's terms of service before enabling automated access. |
| Crawl tuning | `CRAWL_INTERVAL_HOURS`, `CRAWL_MAX_CONCURRENCY` |

Keep `.env` out of Git; it is already git-ignored, and `.dockerignore` keeps it out of images.

---

## A. Local / evaluation stack (Docker Compose)

1. **Configure.** Set `APP_ENV=development` in `.env` (section 3). The dev compose file sets this by default too.
2. **Build and start everything:**
   ```bash
   docker compose up -d --build
   ```
   **On Windows**, add the override file, which runs the Celery worker in solo-pool mode:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d --build
   ```
3. **Create the database tables.** Migrations are **not** run automatically:
   ```bash
   docker compose exec app alembic upgrade head
   ```
   Each user's private schema is created and migrated automatically when they complete onboarding step 1.
4. **Check it's up:**
   ```bash
   docker compose ps                         # every service should be "running"/"healthy"
   curl http://localhost:8000/api/health     # -> 200
   ```
   The interactive API docs are at http://localhost:8000/api/docs (development only). The MinIO console is at http://localhost:9001; the resume bucket is created on first upload.
5. **Sign in.** Open `http://localhost:8000/api/auth/login/google` (or `linkedin` / `facebook`), then complete TOTP enrolment and the onboarding steps.

**Stop:** `docker compose down`. Add `-v` to also delete the database, Redis and MinIO data.

---

## B. Production stack (Docker Compose + nginx)

The full runbook, with the post-deploy smoke tests, is [`deploy-verification.md`](deploy-verification.md). In short:

1. **Configure `.env`** (section 3) with `APP_ENV=production`, real secrets, your public `APP_BASE_URL`, and your admins' IPs in `ALLOWED_IPS`.
2. **TLS certificates.** Put `cert.pem` and `key.pem` in `nginx/ssl/`. Use real certificates in production. For a test host, a self-signed pair works:
   ```bash
   mkdir -p nginx/ssl && openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
     -subj "/CN=jhans-test" -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem
   ```
3. **Build the images.** The production compose file uses tagged images and does not build them. Don't set `APP_IMAGE`: app, worker and beat all read it.
   ```bash
   docker build -t jhans-app:latest -f Dockerfile .
   docker build -t jhans-worker:latest -f Dockerfile.worker .
   ```
4. **Start the stack:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   docker compose -f docker-compose.prod.yml ps
   ```
   Only nginx publishes ports (80 redirects to 443). The app is reachable only through it. nginx has the fixed address `172.28.0.10`, and uvicorn trusts forwarded client IPs only from that address. That's what makes `ALLOWED_IPS` see real client addresses.
5. **Migrate, then reclaim space:**
   ```bash
   docker compose -f docker-compose.prod.yml exec app alembic upgrade head
   docker compose -f docker-compose.prod.yml exec db \
     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "VACUUM FULL users;"'
   ```
   The `VACUUM FULL` clears the pages that held plaintext TOTP secrets before migration `0004` encrypted them. It's only needed once, on a database that existed before `0004`.
6. **Smoke-test:**
   ```bash
   bash scripts/deploy-smoke.sh denied
   ```
   Every test should pass. See [`deploy-verification.md`](deploy-verification.md) for the optional "allowed" run and a troubleshooting table.

### Upgrading an existing install

```bash
git pull
docker build -t jhans-app:latest -f Dockerfile .
docker build -t jhans-worker:latest -f Dockerfile.worker .
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec app alembic upgrade head
bash scripts/deploy-smoke.sh denied
```

Back up the database and `.env` (especially `FERNET_KEY`) before upgrading:

```bash
docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.sql
```

---

## C. Developer setup without Docker (tests only)

This runs the test suite. It does not serve the full product, which needs Redis, MinIO and the worker.

```bash
python -m venv .venv                      # or: uv venv --python 3.12
. .venv/bin/activate                      # Windows: .venv\Scripts\activate
pip install -r requirements.txt           # or: uv pip install -r requirements.txt
python -m playwright install chromium     # only needed to run crawlers for real
pytest -q                                 # unit tests; database tests are skipped
```

**Database integration tests** need a PostgreSQL 16 you can create databases in. Use a throwaway database whose name ends in `_test`; the tests refuse anything else, because they migrate it up and down.

```bash
export RUN_DB_TESTS=1 POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
       POSTGRES_USER=jhans POSTGRES_PASSWORD=<pw> POSTGRES_DB=jhans_test
pytest -q tests/integration
```

Lint and types: `ruff check .` and `mypy app/` (install both with `pip install ruff mypy`).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `app` exits at startup | `docker compose logs app`. Usually a missing required secret (section 3.1), or `APP_ENV` isn't `development`/`production`. |
| `/api/admin/*` returns 403 "Access restricted to authorised server IPs." | Your IP isn't in `ALLOWED_IPS` (exact match), or you changed `.env` without recreating the app: `docker compose up -d app`. In the local stack, requests from the Docker host arrive from the compose network gateway. Find its address with `docker network inspect <project>_default -f '{{(index .IPAM.Config 0).Gateway}}'` and add it. |
| OAuth sign-in fails with `redirect_uri_mismatch` | The redirect URI registered with the provider must exactly match `<APP_BASE_URL>/api/auth/callback/<provider>`. Behind nginx it must be the `https://` URL. |
| Login loops in the local stack | You're on `http://` with `APP_ENV=production`, so the browser drops the https-only session cookie. Use `APP_ENV=development` locally. |
| TOTP code rejected, then HTTP 429 | 5 wrong codes lock TOTP verification for 15 minutes. Check that the phone's clock is set automatically. |
| `alembic upgrade head` fails at `0004` with `InvalidToken` | `FERNET_KEY` differs from the key the data was encrypted with. Restore the original key. |
| Worker errors on Windows about `fork` | Start with the `docker-compose.windows.yml` override. |
| Port 5432/6379/8000 already in use | Stop the local service using it, or change the host side of the port mapping in `docker-compose.yml`. |

## Known limitations

- **No admin account setup.** There's no admin login endpoint or admin-creation command yet. The Windows installer asks for an admin email and password and writes them to `.env` as `BOOTSTRAP_ADMIN_*`, but nothing reads them. Remove them from `.env`; the password sits there in plain text. The `/api/admin/*` endpoints are protected by `ALLOWED_IPS` plus an admin session, and there's currently no way to obtain that session.
- **The Windows installer wizard is not a working install path yet.** It copies only the compose files, which build from source, and runs `docker compose pull`. It also doesn't run migrations. Use option A or B.
- **Consent withdrawal doesn't delete data.** Withdrawing data-processing consent deactivates the account, but no job hard-deletes it after the 30-day deadline. That needs an approved change to `app/compliance/deletion.py`.
- **`FERNET_KEY` can't be rotated.** There's no re-encryption tool yet.
