"""
CHG-003 (risk R17): TOTP verification is bound to a pending-2FA session.
Given a user who has passed OAuth but not yet verified TOTP, when they submit a
code, then the user is identified only by the short-lived signed `pending_2fa`
cookie the OAuth callback issued — never by a caller-supplied user id — and a
normal session token cannot stand in for it.

The rest of app/routers/auth.py (login redirect, per-provider userinfo parsing,
new-user creation, logout) is pinned alongside so the fix cannot regress it.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.dialects import postgresql

from app.database import get_db
from app.dependencies import get_current_user
from app.routers import auth
from app.security.encryption import decrypt, encrypt, sha256_hash
from app.security.rate_limiter import limiter
from app.services.auth_service import (
    create_access_token,
    create_pending_2fa_token,
    decode_access_token,
)

USER_ID = "user-123"
EMAIL = "Asha@Example.com"
SECRET = pyotp.random_base32()
PENDING_PATH = "/api/auth/totp"


class _FakeDB:
    def __init__(self, user):
        self.user = user
        self.statements = []
        self.added = []
        self.commits = 0

    @property
    def queries(self):
        return len(self.statements)

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(scalar_one_or_none=lambda: self.user)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _json(payload):
    return SimpleNamespace(json=lambda: payload)


class _FakeOAuthClient:
    """Answers each provider's userinfo calls from a path -> payload table."""

    def __init__(self, token, pages):
        self.token, self.pages, self.redirect_uri = token, pages, None

    async def authorize_access_token(self, _request):
        return self.token

    async def get(self, path, token=None):
        return _json(self.pages[path.split("?")[0]])

    async def authorize_redirect(self, _request, redirect_uri):
        self.redirect_uri = redirect_uri
        return RedirectResponse("https://provider.example/authorize", status_code=302)


GOOGLE = _FakeOAuthClient({"userinfo": {"email": EMAIL, "sub": "g-1", "name": "Asha"}}, {})


def _user(verified=False, onboarded=False, **lockout):
    return SimpleNamespace(
        id=USER_ID, totp_secret_encrypted=encrypt(SECRET), totp_verified=verified,
        onboarding_complete=onboarded, is_active=True,
        **{"totp_failed_attempts": 0, "totp_locked_until": None,
           "totp_last_used_step": None, **lockout},
    )


@pytest.fixture
def api(monkeypatch):
    env = SimpleNamespace(db=_FakeDB(_user()), events=[], oauth=GOOGLE, providers=[])

    def create_client(provider):
        env.providers.append(provider)
        return env.oauth

    monkeypatch.setattr(auth, "audit", lambda event, **kw: env.events.append(event))
    monkeypatch.setattr(auth.oauth, "create_client", create_client)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth.router)
    app.dependency_overrides[get_db] = lambda: env.db
    limiter.reset()
    env.app, env.client = app, TestClient(app)
    yield env
    limiter.reset()


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _cookies(response, name):
    return [c for c in response.headers.get_list("set-cookie") if c.startswith(f"{name}=")]


def _cookie_value(set_cookie):
    return set_cookie.split(";", 1)[0].split("=", 1)[1].strip('"')


def _callback(api, provider="google"):
    return api.client.get(f"/api/auth/callback/{provider}", follow_redirects=False)


def _verify(api, token=None, code=None, params=None):
    headers = {"Cookie": f"pending_2fa={token}"} if token is not None else {}
    body = {"code": code or pyotp.TOTP(SECRET).now()}
    return api.client.post("/api/auth/totp/verify", json=body, params=params, headers=headers)


def test_verify_refuses_a_code_sent_in_the_query_string(api):
    """Given a valid pending session, when the code is sent in the URL instead of
    the body, then it is refused (422) so one-time codes never reach access logs."""
    token = _cookie_value(_callback(api).headers["set-cookie"])
    resp = api.client.post(
        "/api/auth/totp/verify", params={"code": pyotp.TOTP(SECRET).now()},
        headers={"Cookie": f"pending_2fa={token}"},
    )
    assert resp.status_code == 422
    assert "access_token" not in resp.headers.get("set-cookie", "")


# --- login ------------------------------------------------------------------------

def test_login_redirects_to_the_provider_with_our_callback(api):
    response = api.client.get("/api/auth/login/google", follow_redirects=False)

    assert response.status_code == 302
    assert api.oauth.redirect_uri == "http://testserver/api/auth/callback/google"


@pytest.mark.parametrize("route", ["login", "callback"])
def test_unsupported_provider_is_400_without_an_oauth_client(api, route):
    response = api.client.get(f"/api/auth/{route}/myspace", follow_redirects=False)

    assert response.status_code == 400 and api.providers == []


# --- AC1 / AC7: the OAuth callback -------------------------------------------------

def test_callback_for_unverified_user_sets_a_short_lived_pending_cookie(api):
    response = _callback(api)

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "totp_setup" and body["is_new_user"] is False
    [cookie] = _cookies(response, "pending_2fa")
    attrs = cookie.lower()
    for attr in ("httponly", "secure", "samesite=lax", "max-age=600", f"path={PENDING_PATH}"):
        assert attr in attrs
    claims = decode_access_token(_cookie_value(cookie))
    assert claims["sub"] == USER_ID and claims["purpose"] == "totp_setup"
    assert claims["exp"] - claims["iat"] == 600
    assert _cookies(response, "access_token") == []
    assert api.events == ["auth.totp_setup_required"]


def test_callback_builds_the_provisioning_uri_from_the_decrypted_secret(api):
    """CHG-005 AC3: the stored secret is ciphertext; the QR/URI carry the real one."""
    body = _callback(api).json()

    assert f"secret={SECRET}" in body["totp_uri"] and body["qr_code_base64"]


def test_callback_looks_the_user_up_by_lowercased_email_hash(api):
    _callback(api)

    assert f"users.email_hash = '{sha256_hash(EMAIL.lower())}'" in _sql(api.db.statements[0])


def test_callback_creates_an_unverified_user_on_first_login(api):
    api.db.user = None
    response = _callback(api)

    [created] = api.db.added
    assert created.totp_verified is False and created.oauth_sub == "g-1"
    secret = decrypt(created.totp_secret_encrypted)  # CHG-005 AC3: stored encrypted
    assert len(secret) == 32 and secret.encode() not in created.totp_secret_encrypted
    assert f"secret={secret}" in response.json()["totp_uri"]
    assert created.onboarding_complete is False and created.onboarding_step == 1
    assert created.email_hash == sha256_hash(EMAIL.lower()) and api.db.commits == 1
    assert response.json()["is_new_user"] is True
    [cookie] = _cookies(response, "pending_2fa")
    assert decode_access_token(_cookie_value(cookie))["sub"] == created.id
    assert api.events == ["user.created", "auth.totp_setup_required"]


@pytest.mark.parametrize("onboarded,target", [(True, "/dashboard"), (False, "/onboarding")])
def test_callback_for_verified_user_still_logs_straight_in(api, onboarded, target):
    api.db.user = _user(verified=True, onboarded=onboarded)
    response = _callback(api)

    assert response.status_code == 302 and response.headers["location"] == target
    [cookie] = _cookies(response, "access_token")
    assert "purpose" not in decode_access_token(_cookie_value(cookie))
    attrs = cookie.lower()
    assert "httponly" in attrs and "secure" in attrs and "samesite=lax" in attrs
    assert _cookies(response, "pending_2fa") == []
    assert api.events == ["auth.login"]


LINKEDIN_ME = {"id": "li-7", "localizedFirstName": "Asha", "localizedLastName": "R"}
LINKEDIN_EMAIL = {"elements": [{"handle~": {"emailAddress": EMAIL}}]}
FACEBOOK_ME = {"id": "fb-9", "name": "Asha", "email": EMAIL}


@pytest.mark.parametrize("provider,pages,sub", [
    ("linkedin", {"me": LINKEDIN_ME, "emailAddress": LINKEDIN_EMAIL}, "li-7"),
    ("facebook", {"me": FACEBOOK_ME}, "fb-9"),
])
def test_callback_reads_each_providers_userinfo(api, provider, pages, sub):
    api.db.user, api.oauth = None, _FakeOAuthClient({}, pages)
    response = _callback(api, provider)

    assert response.status_code == 200
    [created] = api.db.added
    assert created.oauth_sub == sub and created.oauth_provider.value == provider
    assert created.email_hash == sha256_hash(EMAIL.lower())


@pytest.mark.parametrize("provider,pages", [
    ("linkedin", {"me": LINKEDIN_ME, "emailAddress": {"elements": []}}),
    ("facebook", {"me": {"id": "fb-9", "name": "Asha"}}),
])
def test_callback_without_an_email_is_400(api, provider, pages):
    api.oauth = _FakeOAuthClient({}, pages)

    assert _callback(api, provider).status_code == 400
    assert api.db.queries == 0


# --- AC2 / AC3: who may call /totp/verify ------------------------------------------

def test_verify_without_pending_cookie_is_401_even_with_a_user_id(api):
    response = _verify(api, params={"user_id": USER_ID})

    assert response.status_code == 401
    assert api.db.queries == 0 and api.db.user.totp_verified is False


@pytest.mark.parametrize("token", [
    create_access_token({"sub": USER_ID}),
    create_access_token({"sub": USER_ID, "purpose": "password_reset"}),
    create_access_token({"sub": USER_ID, "purpose": "totp_setup"}, timedelta(seconds=-1)),
    create_access_token({"purpose": "totp_setup"}),
    create_pending_2fa_token(USER_ID)[:-2] + "xx",
], ids=["session-token", "wrong-purpose", "expired", "no-subject", "bad-signature"])
def test_verify_rejects_anything_but_a_valid_pending_token(api, token):
    response = _verify(api, token=token)

    assert response.status_code == 401
    assert api.db.queries == 0 and api.db.commits == 0


# --- AC4 / AC5: outcome of a verify attempt ----------------------------------------

def test_verify_with_pending_token_and_good_code_opens_a_session(api):
    response = _verify(api, token=create_pending_2fa_token(USER_ID))

    assert response.status_code == 200
    assert response.json() == {"ok": True, "redirect": "/onboarding"}
    assert f"users.id = '{USER_ID}'" in _sql(api.db.statements[0])
    assert _sql(api.db.statements[0]).endswith("FOR UPDATE")  # CHG-006 AC7
    assert api.db.user.totp_verified is True and api.db.commits == 1
    [session] = _cookies(response, "access_token")
    claims = decode_access_token(_cookie_value(session))
    assert claims["sub"] == USER_ID and "purpose" not in claims
    [cleared] = _cookies(response, "pending_2fa")
    assert "max-age=0" in cleared.lower() and f"path={PENDING_PATH}" in cleared.lower()
    assert api.events == ["auth.totp_verified"]


def test_verify_derives_the_user_from_the_cookie_not_a_user_id_param(api):
    response = _verify(api, token=create_pending_2fa_token(USER_ID), params={"user_id": "victim-9"})

    assert response.status_code == 200
    [lookup] = api.db.statements
    assert f"users.id = '{USER_ID}'" in _sql(lookup) and "victim-9" not in _sql(lookup)


def test_pending_token_cannot_be_replayed_once_totp_is_verified(api):
    api.db.user = _user(verified=True)
    response = _verify(api, token=create_pending_2fa_token(USER_ID))

    assert response.status_code == 401
    assert api.db.commits == 0 and _cookies(response, "access_token") == []
    assert api.events == []


def test_verify_for_an_onboarded_user_redirects_to_the_dashboard(api):
    api.db.user = _user(onboarded=True)
    response = _verify(api, token=create_pending_2fa_token(USER_ID))

    assert response.json() == {"ok": True, "redirect": "/dashboard"}


def test_verify_for_a_vanished_user_is_404(api):
    api.db.user = None

    assert _verify(api, token=create_pending_2fa_token(USER_ID)).status_code == 404


def test_verify_with_bad_code_is_400_and_audited(api):
    response = _verify(api, token=create_pending_2fa_token(USER_ID), code="000000x")

    assert response.status_code == 400
    assert api.db.user.totp_verified is False
    assert api.db.user.totp_failed_attempts == 1 and api.db.commits == 1  # CHG-006 AC3
    assert _cookies(response, "access_token") == []
    assert api.events == ["auth.totp_failed"]


def test_verify_keeps_its_rate_limit_of_ten_per_minute(api):
    statuses = [_verify(api).status_code for _ in range(11)]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


# --- CHG-006: per-account lockout and replay guard --------------------------------

def _step_now():
    return int(datetime.now(timezone.utc).timestamp()) // 30


def test_fifth_failure_locks_the_account_and_later_attempts_get_429(api):
    token = create_pending_2fa_token(USER_ID)
    statuses = [_verify(api, token=token, code="000000x").status_code for _ in range(6)]

    assert statuses == [400] * 5 + [429]
    locked_until = api.db.user.totp_locked_until
    assert timedelta(minutes=14) < locked_until - datetime.now(timezone.utc) <= timedelta(minutes=15)
    assert api.events == ["auth.totp_failed"] * 5 + ["auth.totp_locked"]


def test_a_locked_account_is_refused_without_checking_even_a_good_code(api):
    api.db.user = _user(totp_locked_until=datetime.now(timezone.utc) + timedelta(seconds=90))
    response = _verify(api, token=create_pending_2fa_token(USER_ID))

    assert response.status_code == 429
    assert 89 <= int(response.headers["retry-after"]) <= 90
    assert api.db.user.totp_verified is False and api.db.commits == 0
    assert api.db.user.totp_failed_attempts == 0
    assert _cookies(response, "access_token") == []
    assert api.events == ["auth.totp_locked"]


def test_codes_are_checked_again_once_the_lock_has_expired(api):
    api.db.user = _user(totp_locked_until=datetime.now(timezone.utc) - timedelta(seconds=1))

    assert _verify(api, token=create_pending_2fa_token(USER_ID)).status_code == 200


def test_success_resets_the_count_and_remembers_the_step(api):
    api.db.user = _user(totp_failed_attempts=4)
    before = _step_now()
    response = _verify(api, token=create_pending_2fa_token(USER_ID))

    assert response.status_code == 200
    user = api.db.user
    assert user.totp_failed_attempts == 0 and user.totp_locked_until is None
    assert before <= user.totp_last_used_step <= _step_now()


def test_a_code_from_the_last_accepted_step_is_a_replay(api):
    api.db.user = _user(totp_last_used_step=_step_now() + 1)
    response = _verify(api, token=create_pending_2fa_token(USER_ID))

    assert response.status_code == 400
    assert api.db.user.totp_verified is False
    assert api.db.user.totp_failed_attempts == 1 and api.db.commits == 1
    assert _cookies(response, "access_token") == []
    assert api.events == ["auth.totp_failed"]


# --- logout -----------------------------------------------------------------------

def test_logout_clears_the_session_cookie(api):
    api.app.dependency_overrides[get_current_user] = lambda: _user(verified=True)
    response = api.client.post("/api/auth/logout")

    assert response.json() == {"ok": True}
    [cleared] = _cookies(response, "access_token")
    assert "max-age=0" in cleared.lower()
    assert api.events == ["auth.logout"]
