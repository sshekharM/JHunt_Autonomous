"""
Characterisation pins for existing auto-apply behaviour (dispatch filter and
pause handling), so the consent gate added in CHG-007 cannot change them
unnoticed.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.compliance.dpdpa import ConsentRecord
from app.tasks import auto_apply

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


class _FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


class _Shared:
    def __init__(self, users):
        self.users, self.statements = users, []

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile(dialect=postgresql.dialect(),
                                                compile_kwargs={"literal_binds": True})))
        users = self.users
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: users))


class _Tenant:
    def __init__(self, prefs):
        self.prefs, self.executed, self.commits = prefs, 0, 0

    async def execute(self, _stmt):
        self.executed += 1
        prefs = self.prefs
        # Anything after the preferences: no applications today, no jobs.
        value = prefs if self.executed == 1 else (0 if self.executed == 2 else [])
        return SimpleNamespace(scalar_one_or_none=lambda: value, scalar_one=lambda: value,
                               fetchall=lambda: value,
                               scalars=lambda: SimpleNamespace(all=lambda: value))

    async def commit(self):
        self.commits += 1


@pytest.fixture
def world(monkeypatch):
    world = SimpleNamespace(shared=_Shared([]), tenant=None, dispatched=[])

    @asynccontextmanager
    async def session():
        yield world.shared

    async def tenant_db(schema_name):
        yield world.tenant

    async def full_consent(user_id, db):
        return ConsentRecord(consented_to_auto_apply=True, consented_to_llm_processing=True,
                             consented_to_data_processing=True)

    monkeypatch.setattr(auto_apply, "_run", asyncio.run)
    monkeypatch.setattr(auto_apply, "AsyncSessionLocal", session)
    monkeypatch.setattr(auto_apply, "get_tenant_db", tenant_db)
    monkeypatch.setattr(auto_apply, "datetime", _FixedClock)
    monkeypatch.setattr("app.compliance.consent_store.current_consent", full_consent)
    monkeypatch.setattr(auto_apply.apply_matched_jobs, "delay",
                        lambda *args: world.dispatched.append(args))
    return world


def _paused_prefs(until):
    return SimpleNamespace(auto_apply_enabled=True, auto_apply_paused=True, pause_until=until,
                           hitl_enabled=True, apply_cap_daily=5, match_threshold=0.7,
                           llm_choice=SimpleNamespace(value="self_hosted"))


def test_dispatch_sends_one_task_per_active_onboarded_user(world):
    world.shared.users = [SimpleNamespace(id="u1", schema_name="u_a"),
                          SimpleNamespace(id="u2", schema_name="u_b")]
    auto_apply.auto_apply_for_all_users.run()

    assert world.dispatched == [("u1", "u_a"), ("u2", "u_b")]
    sql = world.shared.statements[0]
    assert "WHERE users.is_active = true AND users.onboarding_complete = true" in sql


@pytest.mark.parametrize("until", [None, NOW + timedelta(seconds=1)], ids=["indefinite", "future"])
def test_a_pause_that_has_not_ended_stops_the_run(world, until):
    world.tenant = _Tenant(_paused_prefs(until))
    auto_apply.apply_matched_jobs.run("u1", "u_a")

    assert world.tenant.executed == 1 and world.tenant.commits == 0
    assert world.tenant.prefs.auto_apply_paused is True


@pytest.mark.parametrize("until", [NOW, NOW - timedelta(minutes=1)], ids=["ends_now", "ended"])
def test_a_pause_that_has_ended_is_cleared_and_the_run_goes_on(world, until):
    world.tenant = _Tenant(_paused_prefs(until))
    auto_apply.apply_matched_jobs.run("u1", "u_a")

    assert world.tenant.prefs.auto_apply_paused is False and world.tenant.prefs.pause_until is None
    assert world.tenant.commits == 1 and world.tenant.executed > 1
