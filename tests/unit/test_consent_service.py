"""
CHG-007 AC8/AC10: withdrawing consent stops the processing it covered.
Given a withdrawal of auto_apply, the user's auto-apply preference is switched
off; given a withdrawal of data_processing, the account is scheduled for
deletion through the existing soft-delete entry point.
"""
import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from app.compliance.consent_store import CONSENT_SCOPES, Withdrawal
from app.compliance.deletion import DeletionMode
from app.compliance.dpdpa import ConsentRecord
from app.schemas.consent import DeletionSummary
from app.services import consent_service

USER = SimpleNamespace(id="u1", schema_name="u_abc")
SHARED_DB = object()


class _Tenant:
    def __init__(self, prefs):
        self.prefs, self.commits, self.statements = prefs, 0, []

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        prefs = self.prefs
        return SimpleNamespace(scalar_one_or_none=lambda: prefs)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def wired(monkeypatch):
    """Fake the consent store, the tenant session and the deletion entry point."""
    calls = SimpleNamespace(withdraw=[], tenants=[], deletions=[], withdrawn=(), off=set())
    tenant = _Tenant(SimpleNamespace(auto_apply_enabled=True))

    async def fake_withdraw(user_id, scopes, ip, ua, db):
        calls.withdraw.append((user_id, list(scopes), ip, ua, db))
        flags = {col: scope not in calls.off for scope, col in CONSENT_SCOPES.items()}
        return Withdrawal(record=ConsentRecord(user_id=user_id, **flags), withdrawn=calls.withdrawn)

    async def fake_tenant_db(schema_name):
        calls.tenants.append(schema_name)
        yield tenant

    async def fake_execute_deletion(user, mode, db):
        calls.deletions.append((user, mode, db))
        return {"mode": mode.value, "message": "Account deactivated.",
                "hard_delete_after": "2026-10-25T00:00:00+00:00"}

    monkeypatch.setattr(consent_service.consent_store, "withdraw_consent", fake_withdraw)
    monkeypatch.setattr(consent_service, "get_tenant_db", fake_tenant_db)
    monkeypatch.setattr(consent_service, "execute_deletion", fake_execute_deletion)
    calls.tenant = tenant
    return calls


def _withdraw(scopes):
    return asyncio.run(consent_service.withdraw(USER, scopes, "203.0.113.9", "UA/2", SHARED_DB))


def test_withdrawal_is_recorded_with_the_request_details(wired):
    wired.withdrawn, wired.off = ("llm_processing",), {"llm_processing"}
    outcome = _withdraw(["llm_processing"])

    assert wired.withdraw == [("u1", ["llm_processing"], "203.0.113.9", "UA/2", SHARED_DB)]
    assert outcome.withdrawal.withdrawn == ("llm_processing",)
    assert outcome.account_deletion is None
    assert wired.tenants == [] and wired.deletions == []


def test_withdrawing_auto_apply_switches_the_preference_off(wired):
    wired.withdrawn, wired.off = ("auto_apply",), {"auto_apply"}
    _withdraw(["auto_apply"])

    assert wired.tenants == ["u_abc"]
    assert wired.tenant.prefs.auto_apply_enabled is False and wired.tenant.commits == 1
    assert "FROM preferences" in wired.tenant.statements[0]
    assert wired.deletions == []


def test_withdrawing_data_processing_schedules_account_deletion(wired):
    wired.withdrawn, wired.off = ("data_processing",), {"data_processing"}
    outcome = _withdraw(["data_processing"])

    assert wired.deletions == [(USER, DeletionMode.soft_delete, SHARED_DB)]
    assert outcome.account_deletion == DeletionSummary(
        mode="soft_delete", message="Account deactivated.",
        hard_delete_after="2026-10-25T00:00:00+00:00",
    )


def test_a_retry_after_a_failed_side_effect_completes_it(wired):
    """The consent row is committed first; if switching the preference off or
    scheduling deletion failed, repeating the request must finish the job."""
    wired.withdrawn, wired.off = (), {"auto_apply", "data_processing"}
    outcome = _withdraw(["auto_apply", "data_processing"])

    assert outcome.withdrawal.withdrawn == ()
    assert wired.tenants == ["u_abc"] and wired.tenant.prefs.auto_apply_enabled is False
    assert wired.deletions == [(USER, DeletionMode.soft_delete, SHARED_DB)]


def test_side_effects_follow_only_the_scopes_asked_for(wired):
    wired.withdrawn, wired.off = ("llm_processing",), {"auto_apply", "data_processing", "llm_processing"}
    _withdraw(["llm_processing"])

    assert wired.tenants == [] and wired.deletions == []


def test_disable_auto_apply_leaves_a_user_without_preferences_alone(wired):
    wired.tenant.prefs = None
    asyncio.run(consent_service.disable_auto_apply("u_abc"))
    assert wired.tenant.commits == 0


def test_disable_auto_apply_does_not_rewrite_an_already_disabled_preference(wired):
    wired.tenant.prefs.auto_apply_enabled = False
    asyncio.run(consent_service.disable_auto_apply("u_abc"))
    assert wired.tenant.commits == 0


def test_a_withdrawal_outcome_cannot_be_altered_after_the_fact(wired):
    wired.withdrawn, wired.off = ("llm_processing",), {"llm_processing"}
    outcome = _withdraw(["llm_processing"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.account_deletion = {"mode": "hard_delete"}  # type: ignore[misc]
