"""
Onboarding step 1 establishes a user's permanent identity.
Given a signed-in user submitting personal details, when step 1 runs, then the
thumbprint is derived once from email + phone, the tenant schema is named from it,
that schema is provisioned, and a duplicate identity is refused with 409.

The remaining onboarding steps (2-9 plus status) each mutate the tenant profile
and advance user.onboarding_step; these characterization tests pin the exact
response body and branch behavior of every handler in app/routers/onboarding.py.
"""
import asyncio
import contextlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.security import encryption
from app.routers import onboarding
from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint
from app.tenant_models.profile import LLMChoice, NotificationPlatform

EMAIL, PHONE = "Asha@Example.com", "+91 98765 43210"


class _FakeDB:
    def __init__(self, existing=None):
        self.existing = existing
        self.commits = 0
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return SimpleNamespace(scalar_one_or_none=lambda: self.existing)

    async def commit(self):
        self.commits += 1


class _FakeTenantDB:
    def __init__(self, execute_results=None):
        self.added = []
        self.executed = []
        self.commits = 0
        self._execute_results = list(execute_results or [])

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        if self._execute_results:
            return self._execute_results.pop(0)
        return SimpleNamespace(first=lambda: None)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def wired(monkeypatch):
    calls = SimpleNamespace(provisioned=[], tenant_schemas=[], tenant=_FakeTenantDB())

    async def provision(schema):
        calls.provisioned.append(schema)

    async def tenant_db(schema):
        calls.tenant_schemas.append(schema)
        yield calls.tenant

    @contextlib.asynccontextmanager
    async def tenant_session(schema):
        calls.tenant_schemas.append(schema)
        yield calls.tenant

    monkeypatch.setattr(encryption, "decrypt", lambda _: EMAIL)
    monkeypatch.setattr(onboarding, "provision_user_schema", provision)
    monkeypatch.setattr(onboarding, "get_tenant_db", tenant_db)
    monkeypatch.setattr(onboarding, "tenant_session", tenant_session, raising=False)
    monkeypatch.setattr(onboarding, "audit", lambda *a, **k: None)
    return calls


def _run(db, user):
    data = onboarding.Step1PersonalData(full_name="Asha", phone=PHONE, city="Pune", state="MH")
    return asyncio.run(onboarding.step1_personal(request=None, data=data, user=user, db=db))


def _user():
    return SimpleNamespace(id="u1", email_encrypted=b"x", thumbprint=None, schema_name=None, onboarding_step=1)


def test_step1_sets_identity_from_email_and_phone(wired):
    user = _user()
    result = _run(_FakeDB(), user)

    expected_tp = generate_thumbprint(EMAIL, PHONE)
    expected_schema = schema_name_from_thumbprint(expected_tp)
    assert (user.thumbprint, user.schema_name) == (expected_tp, expected_schema)
    assert result["thumbprint"] == expected_tp
    assert wired.provisioned == [expected_schema]
    assert wired.tenant_schemas == [expected_schema]
    assert len(wired.tenant.added) == 1
    assert user.onboarding_step == 2


def test_step1_returns_full_response_body(wired):
    """Given a fresh user, when step1 completes, then the response body is the
    exact ok/step/thumbprint/notice payload the frontend depends on."""
    user = _user()
    result = _run(_FakeDB(), user)

    expected_tp = generate_thumbprint(EMAIL, PHONE)
    assert result == {
        "ok": True,
        "step": 2,
        "thumbprint": expected_tp,
        "thumbprint_notice": (
            "Your identity thumbprint has been generated from your email and phone number. "
            "This thumbprint is permanent and cannot be changed after signup."
        ),
    }


def test_step1_rejects_duplicate_identity(wired):
    user = _user()
    with pytest.raises(HTTPException) as exc:
        _run(_FakeDB(existing=SimpleNamespace(id="other")), user)
    assert exc.value.status_code == 409
    assert user.thumbprint is None
    assert wired.provisioned == []


def test_step1_duplicate_check_query_predicates(wired):
    """Given the step1 uniqueness check, when its SELECT is compiled, then it
    filters on thumbprint equality AND excludes the current user's own id --
    flipping either operator would silently allow a duplicate or self-lock."""
    user = _user()
    db = _FakeDB()
    _run(db, user)

    expected_tp = generate_thumbprint(EMAIL, PHONE)
    assert len(db.executed) == 1
    compiled = db.executed[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    assert f"users.thumbprint = '{expected_tp}'" in sql
    assert "users.id != 'u1'" in sql


def test_step4_preferences_data_defaults():
    """Given step4 payload omits auto-apply and HITL flags, when the pydantic
    model applies its defaults, then auto-apply is on and human-in-the-loop is off."""
    data = onboarding.Step4PreferencesData(desired_roles=["SWE"], preferred_locations=["Remote"])
    assert data.auto_apply_enabled is True
    assert data.hitl_enabled is False


def _tenant_user():
    return SimpleNamespace(id="u1", schema_name="u_abc", onboarding_step=1, onboarding_complete=False)


def test_step2_professional_updates_and_returns_step3(wired):
    """Given an existing profile row, when step2 submits role/experience, then the
    profile is updated, the step advances to 3, and the response body is pinned."""
    wired.tenant._execute_results = [SimpleNamespace(first=lambda: (1,))]
    user = _tenant_user()
    data = onboarding.Step2ProfessionalData(current_role="Engineer", years_experience=5)

    result = asyncio.run(onboarding.step2_professional(data=data, user=user, db=_FakeDB()))

    assert result == {"ok": True, "step": 3}
    assert user.onboarding_step == 3
    assert len(wired.tenant.executed) == 2


def test_step3_experience_returns_step4(wired):
    user = _tenant_user()
    data = onboarding.Step3ExperienceData(
        work_history=[{"company": "A"}], education=[{"school": "B"}]
    )

    result = asyncio.run(onboarding.step3_experience(data=data, user=user, db=_FakeDB()))

    assert result == {"ok": True, "step": 4}
    assert user.onboarding_step == 4


def test_step4_preferences_returns_step5(wired):
    user = _tenant_user()
    data = onboarding.Step4PreferencesData(desired_roles=["SWE"], preferred_locations=["Remote"])

    result = asyncio.run(onboarding.step4_preferences(data=data, user=user, db=_FakeDB()))

    assert result == {"ok": True, "step": 5}
    assert user.onboarding_step == 5
    assert wired.tenant.added[0].auto_apply_enabled is True
    assert wired.tenant.added[0].hitl_enabled is False


def test_step5_skills_returns_step6(wired):
    user = _tenant_user()
    data = onboarding.Step5SkillsData(skills=[{"skill_name": "Python"}])

    result = asyncio.run(onboarding.step5_skills(data=data, user=user, db=_FakeDB()))

    assert result == {"ok": True, "step": 6}
    assert user.onboarding_step == 6


def _fake_upload_file(content_type="application/pdf", filename="cv.pdf"):
    async def read():
        return b"%PDF-1.4 fake"

    return SimpleNamespace(content_type=content_type, filename=filename, read=read)


def test_step5_resume_upload_rejects_non_pdf(wired):
    """Given a non-PDF upload, when step5's resume handler runs, then it refuses
    with 400 -- flipping != to == would instead accept the wrong content type."""
    user = _tenant_user()
    file = _fake_upload_file(content_type="image/png")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(onboarding.step5_resume_upload(file=file, user=user, db=_FakeDB()))
    assert exc.value.status_code == 400


def test_step5_resume_upload_defaults_filename_when_missing(wired, monkeypatch):
    """Given a PDF with no filename, when step5's resume handler runs, then it
    falls back to "resume.pdf" -- flipping `or` to `and` would store None instead."""
    async def fake_upload(schema, contents, filename):
        return "minio/key/1"

    monkeypatch.setattr(onboarding, "upload_resume", fake_upload)
    user = _tenant_user()
    file = _fake_upload_file(filename=None)

    result = asyncio.run(onboarding.step5_resume_upload(file=file, user=user, db=_FakeDB()))

    assert result == {"ok": True, "minio_key": "minio/key/1"}
    assert wired.tenant.added[0].original_filename == "resume.pdf"


def test_step6_llm_choice_rejects_without_acknowledgment(wired):
    user = _tenant_user()
    data = onboarding.Step6LLMChoiceData(
        llm_choice=LLMChoice.self_hosted, data_processing_acknowledged=False
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(onboarding.step6_llm_choice(data=data, user=user, db=_FakeDB()))
    assert exc.value.status_code == 400


def test_step6_llm_choice_returns_step7(wired):
    user = _tenant_user()
    data = onboarding.Step6LLMChoiceData(
        llm_choice=LLMChoice.self_hosted, data_processing_acknowledged=True
    )

    result = asyncio.run(onboarding.step6_llm_choice(data=data, user=user, db=_FakeDB()))

    assert result == {"ok": True, "step": 7}
    assert user.onboarding_step == 7


def test_step7_notifications_returns_step8(wired):
    user = _tenant_user()
    data = onboarding.Step7NotificationData(
        notification_platform=NotificationPlatform.telegram, telegram_chat_id="123"
    )

    result = asyncio.run(onboarding.step7_notifications(data=data, user=user, db=_FakeDB()))

    assert result == {"ok": True, "step": 8}
    assert user.onboarding_step == 8


def _fake_request(ip="1.2.3.4", ua="pytest-agent"):
    return SimpleNamespace(
        client=SimpleNamespace(host=ip), headers={"user-agent": ua}
    )


def test_step9_consent_rejects_without_data_processing_consent(wired):
    user = _tenant_user()
    data = onboarding.Step9ConsentData(
        consented_to_data_processing=False,
        consented_to_auto_apply=True,
        consented_to_llm_processing=True,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            onboarding.step9_consent(request=_fake_request(), data=data, user=user, db=_FakeDB())
        )
    assert exc.value.status_code == 400


def test_step9_consent_completes_and_redirects(wired, monkeypatch):
    """Given full consent, when step9 runs, then onboarding is marked complete,
    the step advances to 9, and the redirect response body is pinned."""
    recorded = {}

    async def fake_record_consent(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(onboarding, "record_consent", fake_record_consent)
    wired.tenant._execute_results = [SimpleNamespace(first=lambda: ("api",))]
    user = _tenant_user()
    data = onboarding.Step9ConsentData(
        consented_to_data_processing=True,
        consented_to_auto_apply=True,
        consented_to_llm_processing=False,
    )

    result = asyncio.run(
        onboarding.step9_consent(request=_fake_request(), data=data, user=user, db=_FakeDB())
    )

    assert result == {"ok": True, "redirect": "/dashboard"}
    assert user.onboarding_complete is True
    assert user.onboarding_step == 9
    assert recorded["llm_choice"] == "api"
    assert recorded["ip_address"] == "1.2.3.4"


def test_step9_cannot_be_replayed_to_grant_consent_again(wired, monkeypatch):
    """CHG-007: after onboarding, step 9 must not append a fresh grant that would
    silently reverse a consent withdrawal (re-granting is out of scope)."""
    recorded = []

    async def fake_record_consent(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(onboarding, "record_consent", fake_record_consent)
    user = _tenant_user()
    user.onboarding_complete = True
    data = onboarding.Step9ConsentData(
        consented_to_data_processing=True,
        consented_to_auto_apply=True,
        consented_to_llm_processing=True,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            onboarding.step9_consent(request=_fake_request(), data=data, user=user, db=_FakeDB())
        )
    assert exc.value.status_code == 409
    assert recorded == []


def test_get_onboarding_status_reports_user_state():
    user = SimpleNamespace(onboarding_step=3, onboarding_complete=False, thumbprint="tp123")
    result = asyncio.run(onboarding.get_onboarding_status(user=user))
    assert result == {"step": 3, "complete": False, "thumbprint": "tp123"}


def test_get_onboarding_status_reports_missing_thumbprint():
    user = SimpleNamespace(onboarding_step=1, onboarding_complete=False, thumbprint=None)
    result = asyncio.run(onboarding.get_onboarding_status(user=user))
    assert result == {"step": 1, "complete": False, "thumbprint": None}
