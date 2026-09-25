# Deploy and verify (docker-compose.prod.yml)

Run on the Docker host, from the repository root, after the release branch is merged.

## 1. Configure

1. `cp .env.example .env` and fill in real secrets. `APP_ENV=production`, plus `APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `MINIO_SECRET_KEY`, `FERNET_KEY`, and the OAuth client IDs and secrets.
   - **Never change `FERNET_KEY` on an existing database.** TOTP secrets and portal credentials are encrypted with it, and there is no re-encryption tool yet.
   - Leave `JWT_EXPIRY_HOURS` unset (defaults to 4) or set it deliberately.
   - Set `ALLOWED_IPS` to the admin workstations' public IPs, comma-separated with exact matches. **An empty value blocks all admin access.**
2. TLS: put `cert.pem` and `key.pem` in `nginx/ssl/`. For a test host, a self-signed pair is enough:
   ```bash
   mkdir -p nginx/ssl && openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
     -subj "/CN=jhans-test" -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem
   ```

## 2. Build and start

The prod compose file pulls images by tag; it does not build them. Don't set `APP_IMAGE`, because app, worker and beat all read it.

```bash
docker build -t jhans-app:latest -f Dockerfile .
docker build -t jhans-worker:latest -f Dockerfile.worker .
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps        # app should become healthy
```

nginx is pinned to `172.28.0.10` on the stack network, and uvicorn trusts `X-Forwarded-For` only from that address. If `172.28.0.0/24` collides with a network on the host, change the subnet, nginx's `ipv4_address` and the app's `--forwarded-allow-ips` together.

## 3. Migrate

Deploy the app code and the migrations together: `0004` replaces the plaintext `totp_secret` column.

```bash
docker compose -f docker-compose.prod.yml exec app alembic upgrade head
# after 0004, reclaim the pages that held plaintext TOTP secrets:
docker compose -f docker-compose.prod.yml exec db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "VACUUM FULL users;"'
```

Tenant schemas are migrated per user at signup; no manual step is needed.

## 4. Smoke-test the running stack

`scripts/deploy-smoke.sh` runs `tests/deploy/` from a throwaway container of the app image at the fixed address `172.28.0.50` on the stack network. It talks to nginx over HTTPS, the way a browser would.

**Run A: denied (normal configuration).** `172.28.0.50` is not in `ALLOWED_IPS`:
```bash
bash scripts/deploy-smoke.sh denied
```
This checks:
- HTTP redirects to HTTPS, and `/api/health` answers through nginx;
- API docs are off;
- admin requests return 403 from the IP allowlist;
- forged `X-Forwarded-For`, `X-Real-IP` and `Forwarded` headers claiming an allowed IP are still refused;
- the notifications WebSocket upgrades through nginx for the user's own session, and is refused with no session or another user's.

**Run B: allowed (optional, proves the allowlist admits a listed client).**
```bash
# temporarily add 172.28.0.50 to ALLOWED_IPS in .env, then recreate the app:
docker compose -f docker-compose.prod.yml up -d app
bash scripts/deploy-smoke.sh allowed      # admin now passes the IP check -> 401 (login required)
# remove 172.28.0.50 from ALLOWED_IPS again and recreate the app
docker compose -f docker-compose.prod.yml up -d app
```

Expected: every test passes. The skips reported by `-rs` are the checks that only apply to the other run.

## If something fails

| Symptom | Likely cause |
|---|---|
| Admin returns 403 in run B | `ALLOWED_IPS` not reloaded (recreate `app`), or uvicorn isn't trusting nginx: check `--forwarded-allow-ips 172.28.0.10` and nginx's fixed IP |
| Forged-header test gets 401 in run A | uvicorn trusts forwarded headers from everyone (`FORWARDED_ALLOW_IPS=*` in `.env`). Remove it |
| WebSocket test gets 404/400/502 instead of 403 | nginx isn't proxying the upgrade; check `location /api/notifications/ws/` in `nginx/nginx.conf` |
| WebSocket success test gets 403 | `DEPLOY_APP_SECRET_KEY` doesn't match the running app's `APP_SECRET_KEY` |
| `app` unhealthy | `docker compose logs app`; usually a missing secret in `.env` (the app refuses to start without them) |
