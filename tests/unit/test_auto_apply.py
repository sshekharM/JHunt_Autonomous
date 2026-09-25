"""
CHG-007 AC8/AC9/AC11: withdrawn consent stops automated processing.
Given a user whose current consent does not allow auto-apply, the apply task
touches nothing of theirs. Given one who withdrew LLM processing, no resume is
tailored and no cover letter written (their data never reaches an LLM
provider), while queuing jobs for human review still runs.
"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.compliance.dpdpa import ConsentRecord
from app.services import application_service, cover_letter_service, resume_service
from app.tasks import auto_apply

SHARED = object()


def _consent(auto=True, llm=True, data=True):
    return ConsentRecord(user_id="u1", consented_to_auto_apply=auto,
                         consented_to_llm_processing=llm, consented_to_data_processing=data)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def fetchall(self):
        return self.value

    def scalars(self):
        return SimpleNamespace(all=lambda: self.value)


class _Tenant:
    def __init__(self, *answers):
        self.answers, self.executed = list(answers), 0

    async def execute(self, _stmt):
        self.executed += 1
        return _Result(self.answers.pop(0))

    async def commit(self):
        pass


class _World:
    """What the task sees: consent, a tenant session, and the services it calls."""

    def __init__(self):
        self.consent, self.tenant = _consent(), _Tenant()
        self.tenants, self.audits, self.hitl, self.llm_calls = [], [], [], []

    @asynccontextmanager
    async def session(self):
        yield SHARED

    async def current_consent(self, user_id, db):
        assert (user_id, db) == ("u1", SHARED)
        return self.consent

    async def tenant_db(self, schema_name):
        self.tenants.append(schema_name)
        yield self.tenant

    async def queue_for_hitl(self, **kwargs):
        self.hitl.append(kwargs["job_id"])

    async def llm(self, *args, **kwargs):
        self.llm_calls.append(kwargs)
        raise AssertionError("LLM path must not run")

    async def notify(self, **kwargs):
        pass


def _prefs(hitl=False):
    return SimpleNamespace(auto_apply_enabled=True, auto_apply_paused=False, pause_until=None,
                           apply_cap_daily=5, match_threshold=0.7, hitl_enabled=hitl,
                           llm_choice=SimpleNamespace(value="self_hosted"))


def _job():
    return SimpleNamespace(id="j1", match_score=0.9, portal="naukri", portal_job_id="n-1",
                           title="Python Dev", company="Acme", description_snippet="")


@pytest.fixture
def task(monkeypatch):
    world = _World()
    patches = [
        (auto_apply, "_run", asyncio.run), (auto_apply, "AsyncSessionLocal", world.session),
        (auto_apply.consent_store, "current_consent", world.current_consent),
        (auto_apply, "get_tenant_db", world.tenant_db),
        (auto_apply, "audit", lambda event, **kw: world.audits.append((event, kw))),
        (application_service, "queue_for_hitl", world.queue_for_hitl),
        (auto_apply.notification_service, "notify", world.notify),
        (resume_service, "parse_master_resume", world.llm),
        (resume_service, "generate_tailored_resume", world.llm),
        (cover_letter_service, "generate_cover_letter", world.llm),
    ]
    for target, name, value in patches:
        monkeypatch.setattr(target, name, value)
    return world


def _apply():
    auto_apply.apply_matched_jobs.run("u1", "u_abc")


def _enforced(scope):
    return ("consent.enforced", {"user_id": "u1", "details": {"scope": scope, "task": "auto_apply"}})


@pytest.mark.parametrize("consent", [
    _consent(auto=False), _consent(data=False), None,
], ids=["auto_apply_withdrawn", "data_processing_withdrawn", "no_consent_record"])
def test_without_auto_apply_consent_nothing_of_the_user_is_touched(task, consent):
    task.consent = consent
    _apply()

    assert task.tenants == []
    assert task.audits == [_enforced("auto_apply")]


def test_llm_withdrawn_stops_before_any_job_is_loaded(task):
    task.consent = _consent(llm=False)
    task.tenant = _Tenant(_prefs(hitl=False))
    _apply()

    assert task.tenant.executed == 1  # the preferences only
    assert task.llm_calls == []
    assert task.audits == [_enforced("llm_processing")]


def test_llm_withdrawn_still_queues_jobs_for_human_review(task):
    task.consent = _consent(llm=False)
    task.tenant = _Tenant(_prefs(hitl=True), 0, [], [_job()], None, None)
    _apply()

    assert task.hitl == ["j1"] and task.llm_calls == [] and task.audits == []


def test_full_consent_goes_on_to_the_resume_tailoring_path(task):
    task.tenant = _Tenant(_prefs(hitl=False), 0, [], [_job()], None,
                          SimpleNamespace(minio_key="k"))
    _apply()

    assert task.audits == [] and len(task.llm_calls) == 1  # parse_master_resume reached
