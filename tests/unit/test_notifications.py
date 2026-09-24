"""
CHG-004 (risk R18): the notifications WebSocket admits only the user it names.
Given a WebSocket handshake to /api/notifications/ws/{user_id}, when it does not
carry a valid session cookie for exactly that user, then it is closed with 1008
before being accepted or registered; an authorised socket is registered, pinged,
and removed again on disconnect without disturbing the user's other sockets.
"""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from app.routers import notifications
from app.services.auth_service import create_access_token, create_pending_2fa_token

USER_ID = "user-123"
POLICY_VIOLATION = 1008


class _FakeWS:
    def __init__(self, token=None):
        self.cookies = {"access_token": token} if token is not None else {}
        self.accepted = False
        self.closed_with = None
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=None):
        self.closed_with = code

    async def send_json(self, data):
        self.sent.append(data)


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setattr(notifications, "_connections", {})
    _disconnect_after_one_ping(monkeypatch)  # never really wait 30s in a test
    return notifications._connections


def _session(sub=USER_ID):
    return create_access_token({"sub": sub})


def _disconnect_after_one_ping(monkeypatch, before_disconnect=lambda: None):
    """Let the keep-alive loop run once, then simulate the client going away."""
    calls = []

    async def sleep(seconds):
        calls.append(seconds)
        if len(calls) > 1:
            before_disconnect()
            raise WebSocketDisconnect(code=1000)

    monkeypatch.setattr(notifications, "asyncio", SimpleNamespace(sleep=sleep))
    return calls


def _connect(ws, user_id=USER_ID):
    asyncio.run(notifications.notification_ws(ws, user_id))


# --- AC1 / AC2: who is refused ----------------------------------------------------

@pytest.mark.parametrize("token", [
    None,
    "not-a-jwt",
    create_access_token({"sub": USER_ID}, timedelta(seconds=-1)),
    create_pending_2fa_token(USER_ID),
    create_access_token({"sub": "someone-else"}),
], ids=["no-cookie", "garbage", "expired", "pending-2fa", "other-user"])
def test_unauthorised_handshake_is_closed_1008_unaccepted_and_unregistered(token, registry):
    ws = _FakeWS(token)
    _connect(ws)

    assert ws.closed_with == POLICY_VIOLATION
    assert ws.accepted is False and ws.sent == []
    assert registry == {}


def test_handshake_over_http_is_rejected_with_1008():
    app = FastAPI()
    app.include_router(notifications.router)
    with pytest.raises(WebSocketDisconnect) as exc:
        with TestClient(app).websocket_connect(f"/api/notifications/ws/{USER_ID}"):
            pass

    assert exc.value.code == POLICY_VIOLATION


# --- AC3 / AC4: an authorised socket ----------------------------------------------

def test_authorised_socket_is_registered_pinged_then_removed(monkeypatch, registry):
    ws = _FakeWS(_session())
    seen = []
    calls = _disconnect_after_one_ping(monkeypatch, lambda: seen.append(list(registry[USER_ID])))
    _connect(ws)

    assert ws.accepted is True and ws.closed_with is None
    assert ws.sent == [{"type": "ping"}] and calls == [30, 30]
    assert seen == [[ws]]
    assert registry == {}


def test_disconnect_keeps_the_users_other_sockets(monkeypatch, registry):
    other = _FakeWS(_session())
    registry[USER_ID] = [other]
    _disconnect_after_one_ping(monkeypatch)
    _connect(_FakeWS(_session()))

    assert registry == {USER_ID: [other]}


@pytest.mark.parametrize("tamper", [
    lambda reg: reg.clear(),
    lambda reg: reg[USER_ID].clear(),
], ids=["entry-gone", "socket-gone"])
def test_disconnect_with_a_missing_registry_entry_does_not_raise(monkeypatch, registry, tamper):
    _disconnect_after_one_ping(monkeypatch, lambda: tamper(registry))
    _connect(_FakeWS(_session()))

    assert registry == {}


def test_push_reaches_every_registered_socket_of_that_user_only(registry):
    mine, theirs = _FakeWS(), _FakeWS()
    registry.update({USER_ID: [mine], "someone-else": [theirs]})
    asyncio.run(notifications.push_to_user(USER_ID, {"type": "match"}))

    assert mine.sent == [{"type": "match"}] and theirs.sent == []


class _DeadWS(_FakeWS):
    async def send_json(self, data):
        raise RuntimeError("socket already closed")


def test_push_logs_a_failed_socket_and_still_reaches_the_rest(monkeypatch, registry):
    warnings = []
    monkeypatch.setattr(notifications, "logger", SimpleNamespace(
        warning=lambda event, **kw: warnings.append((event, kw["user_id"], kw["exc_info"]))))
    alive = _FakeWS()
    registry[USER_ID] = [_DeadWS(), alive]
    asyncio.run(notifications.push_to_user(USER_ID, {"type": "match"}))

    assert alive.sent == [{"type": "match"}]
    assert warnings == [("notifications.ws_push_failed", USER_ID, True)]


# --- REST handlers (pinned; unchanged by CHG-004) ----------------------------------

class _FakeTenantDB:
    def __init__(self, result=None):
        self.result = result
        self.executed = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return self.result

    async def commit(self):
        self.commits += 1


@pytest.fixture
def tenant(monkeypatch):
    env = SimpleNamespace(db=_FakeTenantDB(), schemas=[])

    async def get_tenant_db(schema):
        env.schemas.append(schema)
        yield env.db

    monkeypatch.setattr(notifications, "get_tenant_db", get_tenant_db)
    return env


SIGNED_IN = SimpleNamespace(id=USER_ID, schema_name="u_" + "a" * 32)


def test_list_returns_the_latest_notifications_as_dicts(tenant):
    row = ("n-1", "match", "email", "New match", True, False, "2026-09-24 10:00:00")
    tenant.db.result = SimpleNamespace(fetchall=lambda: [row])

    assert asyncio.run(notifications.list_notifications(user=SIGNED_IN)) == [{
        "id": "n-1", "event_type": "match", "channel": "email", "subject": "New match",
        "delivered": True, "read": False, "sent_at": "2026-09-24 10:00:00",
    }]
    assert tenant.schemas == [SIGNED_IN.schema_name]


def test_mark_read_updates_one_row_and_commits(tenant):
    assert asyncio.run(notifications.mark_read("n-1", user=SIGNED_IN)) == {"ok": True}
    [(sql, params)] = tenant.db.executed
    assert "SET read=true WHERE id=:id" in sql and params == {"id": "n-1"}
    assert tenant.db.commits == 1


def test_unread_count_reports_the_scalar(tenant):
    tenant.db.result = SimpleNamespace(scalar_one=lambda: 4)

    assert asyncio.run(notifications.unread_count(user=SIGNED_IN)) == {"unread": 4}


def test_mark_all_read_updates_unread_rows_and_commits(tenant):
    assert asyncio.run(notifications.mark_all_read(user=SIGNED_IN)) == {"ok": True}
    [(sql, _)] = tenant.db.executed
    assert "SET read=true WHERE read=false" in sql and tenant.db.commits == 1
