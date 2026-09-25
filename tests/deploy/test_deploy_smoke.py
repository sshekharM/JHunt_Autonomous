"""
Post-deploy smoke tests against a running docker-compose.prod.yml stack.

They exercise what unit tests cannot: nginx -> uvicorn proxy trust, the admin IP
allowlist as seen from a real client, and the notifications WebSocket upgrade
through nginx. Opt-in only (RUN_DEPLOY_TESTS=1); see docs/deploy-verification.md.

Environment:
  DEPLOY_BASE_URL        https URL of nginx (default https://localhost)
  DEPLOY_VERIFY_TLS      "1" to verify the certificate (default: off, self-signed OK)
  DEPLOY_EXPECT_ADMIN    "allowed" if this machine's IP is in ALLOWED_IPS, "denied" if not
  DEPLOY_SPOOF_IP        an IP that IS in ALLOWED_IPS, used to forge headers (default 127.0.0.1)
  DEPLOY_APP_SECRET_KEY  the stack's APP_SECRET_KEY; enables the WebSocket success test
"""
import asyncio
import os
import ssl
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DEPLOY_TESTS") != "1",
    reason="needs a running prod stack; set RUN_DEPLOY_TESTS=1 (docs/deploy-verification.md)",
)

BASE = os.environ.get("DEPLOY_BASE_URL", "https://localhost").rstrip("/")
VERIFY = os.environ.get("DEPLOY_VERIFY_TLS") == "1"
EXPECT_ADMIN = os.environ.get("DEPLOY_EXPECT_ADMIN", "")
SPOOF_IP = os.environ.get("DEPLOY_SPOOF_IP", "127.0.0.1")
SECRET = os.environ.get("DEPLOY_APP_SECRET_KEY", "")
ADMIN_PATH = "/api/admin/ops/dashboard"
IP_DENIED = "Access restricted to authorised server IPs."


def _get(path: str, **kwargs) -> httpx.Response:
    with httpx.Client(verify=VERIFY, follow_redirects=False, timeout=15) as client:
        return client.get(BASE + path, **kwargs)


def _ws_url(path: str) -> str:
    parts = urlsplit(BASE)
    return urlunsplit(("wss" if parts.scheme == "https" else "ws", parts.netloc, path, "", ""))


def _ssl_context() -> ssl.SSLContext | None:
    if not BASE.startswith("https"):
        return None
    ctx = ssl.create_default_context()
    if not VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _token(sub: str) -> str:
    from jose import jwt
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(minutes=5)}, SECRET, algorithm="HS256")


async def _ws_status(path: str, cookie: str | None) -> int:
    """101 when the upgrade succeeds, else the HTTP status the server refused with."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    headers = {"Cookie": cookie} if cookie else None
    try:
        async with connect(_ws_url(path), ssl=_ssl_context(), additional_headers=headers, open_timeout=15):
            return 101
    except InvalidStatus as exc:
        return exc.response.status_code


# --- nginx / app basics -------------------------------------------------------

def test_plain_http_redirects_to_https():
    parts = urlsplit(BASE)
    http_base = urlunsplit(("http", parts.hostname or "localhost", "/", "", ""))
    with httpx.Client(follow_redirects=False, timeout=15) as client:
        resp = client.get(http_base)
    assert resp.status_code == 301
    assert resp.headers["location"].startswith("https://")


def test_health_is_served_through_nginx():
    resp = _get("/api/health")
    assert resp.status_code == 200, resp.text


def test_api_docs_are_disabled_in_production():
    assert _get("/api/docs").status_code == 404
    assert _get("/api/redoc").status_code == 404


# --- admin IP allowlist (R5) ------------------------------------------------------

def test_admin_allowlist_matches_this_client():
    if EXPECT_ADMIN not in ("allowed", "denied"):
        pytest.skip("set DEPLOY_EXPECT_ADMIN=allowed|denied")
    resp = _get(ADMIN_PATH)
    if EXPECT_ADMIN == "denied":
        assert resp.status_code == 403 and resp.json()["detail"] == IP_DENIED
    else:
        # past the IP check, stopped by admin authentication instead
        assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-For": "{ip}"},
    {"X-Forwarded-For": "{ip}, {ip}"},
    {"X-Real-IP": "{ip}"},
    {"X-Forwarded-For": "{ip}", "X-Real-IP": "{ip}", "Forwarded": "for={ip}"},
])
def test_forged_client_ip_headers_do_not_bypass_the_allowlist(headers):
    if EXPECT_ADMIN != "denied":
        pytest.skip("run from a machine NOT in ALLOWED_IPS with DEPLOY_EXPECT_ADMIN=denied")
    forged = {k: v.format(ip=SPOOF_IP) for k, v in headers.items()}
    resp = _get(ADMIN_PATH, headers=forged)
    assert resp.status_code == 403 and resp.json()["detail"] == IP_DENIED


# --- notifications WebSocket through nginx (R18) ----------------------------------

def test_websocket_without_a_session_is_refused_by_the_app():
    # 403 comes from the app closing before accept(); 404/400/502 would mean nginx
    # never proxied the upgrade to it.
    assert asyncio.run(_ws_status("/api/notifications/ws/deploy-smoke-user", None)) == 403


def test_websocket_with_the_users_own_session_upgrades():
    if not SECRET:
        pytest.skip("set DEPLOY_APP_SECRET_KEY to the stack's APP_SECRET_KEY")
    cookie = f"access_token={_token('deploy-smoke-user')}"
    assert asyncio.run(_ws_status("/api/notifications/ws/deploy-smoke-user", cookie)) == 101


def test_websocket_with_another_users_session_is_refused():
    if not SECRET:
        pytest.skip("set DEPLOY_APP_SECRET_KEY to the stack's APP_SECRET_KEY")
    cookie = f"access_token={_token('someone-else')}"
    assert asyncio.run(_ws_status("/api/notifications/ws/deploy-smoke-user", cookie)) == 403
