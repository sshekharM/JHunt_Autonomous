"""
CHG-007 AC6/AC7: a logged-in user can see their consent and withdraw it.
Given a logged-in user, GET /api/consent shows the current flags and history
without network identifiers, and POST /api/consent/withdraw withdraws the
listed scopes; bad scope lists are 422 and a user with no consent is 409.
"""
import typing
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.compliance.consent_store import CONSENT_SCOPES, NoConsentOnRecord, Withdrawal
from app.compliance.dpdpa import ConsentRecord
from app.database import get_db
from app.dependencies import get_current_user
from app.routers import consent
from app.schemas.consent import ConsentScope
from app.services.consent_service import WithdrawalOutcome

USER = SimpleNamespace(id="u1", schema_name="u_abc")
DB = object()
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _record(event="granted", auto=True, llm=True, data=True, at=T0):
    return ConsentRecord(
        user_id="u1", event=event, ip_address="198.51.100.1", user_agent="Secret-UA",
        consented_to_auto_apply=auto, consented_to_llm_processing=llm,
        consented_to_data_processing=data, consented_at=at,
        consent_version="1.0", consent_text_hash="h" * 64, llm_choice="self_hosted",
    )


async def _no_db():
    yield DB


def _client(authenticated=True):
    app = FastAPI()
    app.include_router(consent.router)
    app.dependency_overrides[get_db] = _no_db
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app)


@pytest.fixture
def store(monkeypatch):
    fake = SimpleNamespace(history=[], withdraw_calls=[], outcome=None, error=None)

    async def fake_history(user_id, db):
        assert (user_id, db) == ("u1", DB)
        return fake.history

    async def fake_withdraw(user, scopes, ip, ua, db):
        fake.withdraw_calls.append((user, list(scopes), ip, ua, db))
        if fake.error:
            raise fake.error
        return fake.outcome

    monkeypatch.setattr(consent.consent_store, "consent_history", fake_history)
    monkeypatch.setattr(consent.consent_service, "withdraw", fake_withdraw)
    return fake


def test_the_scope_type_lists_exactly_the_consent_scopes():
    assert set(typing.get_args(ConsentScope)) == set(CONSENT_SCOPES)


def test_get_consent_shows_current_flags_and_history_without_network_identifiers(store):
    later = datetime(2026, 9, 2, tzinfo=timezone.utc)
    store.history = [_record(), _record(event="withdrawn", auto=False, at=later)]

    response = _client().get("/api/consent")

    assert response.status_code == 200
    body = response.json()
    assert body["current"] == {"auto_apply": False, "llm_processing": True, "data_processing": True}
    assert body["history"] == [
        {"event": "granted", "at": "2026-09-01T00:00:00Z",
         "flags": {"auto_apply": True, "llm_processing": True, "data_processing": True}},
        {"event": "withdrawn", "at": "2026-09-02T00:00:00Z",
         "flags": {"auto_apply": False, "llm_processing": True, "data_processing": True}},
    ]
    assert "198.51.100.1" not in response.text and "Secret-UA" not in response.text


def test_get_consent_without_any_record(store):
    response = _client().get("/api/consent")
    assert response.status_code == 200
    assert response.json() == {"current": None, "history": []}


def test_withdraw_passes_the_request_details_and_returns_the_new_flags(store):
    store.outcome = WithdrawalOutcome(
        withdrawal=Withdrawal(record=_record(event="withdrawn", llm=False),
                              withdrawn=("llm_processing",)),
        account_deletion=None,
    )

    response = _client().post("/api/consent/withdraw", json={"scopes": ["llm_processing"]},
                              headers={"user-agent": "Browser/2"})

    assert response.status_code == 200
    assert response.json() == {
        "withdrawn": ["llm_processing"],
        "current": {"auto_apply": True, "llm_processing": False, "data_processing": True},
        "account_deletion": None,
    }
    assert store.withdraw_calls == [(USER, ["llm_processing"], "testclient", "Browser/2", DB)]


def test_withdrawing_data_processing_returns_the_deletion_summary(store):
    summary = {"mode": "soft_delete", "hard_delete_after": "2026-10-25T00:00:00+00:00"}
    store.outcome = WithdrawalOutcome(
        withdrawal=Withdrawal(record=_record(event="withdrawn", data=False),
                              withdrawn=("data_processing",)),
        account_deletion=summary,
    )

    response = _client().post("/api/consent/withdraw", json={"scopes": ["data_processing"]})

    assert response.status_code == 200 and response.json()["account_deletion"] == summary


def test_a_repeated_withdrawal_is_still_200_with_nothing_withdrawn(store):
    store.outcome = WithdrawalOutcome(
        withdrawal=Withdrawal(record=_record(event="withdrawn", auto=False), withdrawn=()),
        account_deletion=None,
    )
    response = _client().post("/api/consent/withdraw", json={"scopes": ["auto_apply"]})
    assert response.status_code == 200 and response.json()["withdrawn"] == []


@pytest.mark.parametrize("body", [
    {"scopes": []}, {"scopes": ["marketing"]}, {"scopes": ["auto_apply", "marketing"]},
    {"scopes": "auto_apply"}, {}, {"scopes": ["auto_apply"], "extra": 1},
])
def test_bad_scope_lists_are_422_and_never_reach_the_service(store, body):
    response = _client().post("/api/consent/withdraw", json=body)
    assert response.status_code == 422
    assert store.withdraw_calls == []


def test_withdraw_without_consent_on_record_is_409(store):
    store.error = NoConsentOnRecord("u1")
    response = _client().post("/api/consent/withdraw", json={"scopes": ["auto_apply"]})
    assert response.status_code == 409


@pytest.mark.parametrize("method,path", [("get", "/api/consent"), ("post", "/api/consent/withdraw")])
def test_endpoints_need_a_logged_in_user(store, method, path):
    client = _client(authenticated=False)
    response = getattr(client, method)(path, json={"scopes": ["auto_apply"]}) if method == "post" \
        else client.get(path)
    assert response.status_code == 401
    assert store.withdraw_calls == []


def test_the_router_is_registered_in_the_app():
    from app.main import app
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/api/consent", "GET") in paths and ("/api/consent/withdraw", "POST") in paths
