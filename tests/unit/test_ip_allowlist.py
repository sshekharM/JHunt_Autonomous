"""
CHG-002: the admin IP allowlist (ALLOWED_IPS) is enforced on every /api/admin route.
Given a caller's IP address, when it calls an admin endpoint, then the request is
refused unless that IP is listed. An empty allowlist refuses everyone.
"""
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import settings
from app.security.ip_allowlist import require_server_ip

ADMIN_PATH = "/api/admin/ops/dashboard"
TESTCLIENT_HOST = "testclient"  # the client address Starlette's TestClient reports


def _request(host):
    return SimpleNamespace(client=SimpleNamespace(host=host) if host is not None else None)


@pytest.fixture
def allow(monkeypatch):
    def _set(value: str) -> None:
        monkeypatch.setattr(settings, "allowed_ips", value)
    return _set


@pytest.fixture
def admin_api():
    from app.main import app
    return TestClient(app)


def _depends_on(dependant, target) -> bool:
    return any(d.call is target or _depends_on(d, target) for d in dependant.dependencies)


# AC1
def test_every_admin_route_depends_on_require_server_ip():
    from app.main import app
    admin_routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/admin")]
    assert admin_routes, "expected admin routes to be registered"
    unguarded = [r.path for r in admin_routes if not _depends_on(r.dependant, require_server_ip)]
    assert unguarded == [], f"admin routes missing the IP allowlist: {unguarded}"


def _admin_endpoints():
    from app.main import app
    return [
        (sorted(r.methods)[0], re.sub(r"\{[^}]+\}", "x", r.path))
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/admin")
    ]


# AC1 + AC2
@pytest.mark.parametrize(("method", "path"), _admin_endpoints())
def test_every_admin_endpoint_refuses_an_unlisted_ip(admin_api, allow, method, path):
    allow("10.0.0.1")
    response = admin_api.request(method, path)
    assert response.status_code == 403


# AC2
def test_admin_route_from_unlisted_ip_is_forbidden_before_auth(admin_api, allow):
    allow("10.0.0.1")
    response = admin_api.get(ADMIN_PATH)
    assert response.status_code == 403
    assert response.json()["detail"] == "Access restricted to authorised server IPs."


# AC3
def test_admin_route_from_listed_ip_proceeds_to_authentication(admin_api, allow):
    allow(f"10.0.0.1, {TESTCLIENT_HOST}")
    response = admin_api.get(ADMIN_PATH)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


# AC3
def test_listed_ip_passes_the_check(allow):
    allow("10.0.0.1,10.0.0.2")
    assert require_server_ip(_request("10.0.0.2")) is None


# AC4
def test_allowlist_parsing_strips_whitespace_and_drops_blanks(allow):
    allow(" 10.0.0.1 , ,10.0.0.2,")
    assert settings.allowed_ip_list == ["10.0.0.1", "10.0.0.2"]


# AC5
@pytest.mark.parametrize("value", ["", "   ", " , ,"])
def test_empty_allowlist_parses_to_no_entries(allow, value):
    allow(value)
    assert settings.allowed_ip_list == []


@pytest.mark.parametrize("host", ["127.0.0.1", "", None])
def test_empty_allowlist_denies_every_request(allow, host):
    allow("")
    with pytest.raises(HTTPException) as exc:
        require_server_ip(_request(host))
    assert exc.value.status_code == 403


def test_request_without_client_address_is_denied(allow):
    allow("127.0.0.1")
    with pytest.raises(HTTPException) as exc:
        require_server_ip(_request(None))
    assert exc.value.status_code == 403
