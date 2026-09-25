"""
CHG-007: DPDPA consent withdrawal (DPDP Act 2023 s.6(4)).
Given a user with consent on record, when they withdraw one or more scopes,
then a NEW consent row records the result (old rows untouched), the
withdrawal is audited without network identifiers, and repeating it is a no-op.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.compliance import consent_store
from app.compliance.consent_store import (
    CONSENT_SCOPES,
    NoConsentOnRecord,
    consent_allows,
    consent_history,
    current_consent,
    withdraw_consent,
)
from app.compliance.dpdpa import ConsentRecord

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _grant(**overrides) -> ConsentRecord:
    fields = {
        "user_id": "u1", "consent_version": "1.0", "ip_address": "198.51.100.1",
        "user_agent": "Onboard/1", "consented_to_data_processing": True,
        "consented_to_auto_apply": True, "consented_to_llm_processing": True,
        "llm_choice": "self_hosted", "consent_text_hash": "h" * 64, "event": "granted",
        "consented_at": T0,
    }
    return ConsentRecord(**{**fields, **overrides})


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Answers each execute() with the next queued row list and records the SQL."""

    def __init__(self, *answers):
        self.answers, self.statements = list(answers), []
        self.added, self.commits = [], 0

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile(dialect=postgresql.dialect())))
        return _Result(self.answers.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def audited(monkeypatch):
    calls = []
    monkeypatch.setattr(consent_store, "audit", lambda event, **kw: calls.append((event, kw)))
    return calls


def _withdraw(db, scopes, ip="203.0.113.9", ua="Browser/2"):
    return asyncio.run(withdraw_consent("u1", scopes, ip, ua, db))


# --- AC2: reading the current consent and the history ----------------------

def test_current_consent_returns_the_latest_record_for_the_user():
    latest = _grant(event="withdrawn")
    db = _FakeDB([latest])

    assert asyncio.run(current_consent("u1", db)) is latest
    sql = db.statements[0]
    assert "consent_records.user_id = %(user_id_1)s" in sql
    assert "ORDER BY consent_records.consented_at DESC" in sql and "LIMIT" in sql


def test_current_consent_is_none_without_a_record():
    assert asyncio.run(current_consent("u1", _FakeDB([]))) is None


def test_consent_history_returns_every_record_oldest_first():
    rows = [_grant(), _grant(event="withdrawn")]
    db = _FakeDB(rows)

    assert asyncio.run(consent_history("u1", db)) == rows
    assert "ORDER BY consent_records.consented_at ASC" in db.statements[0]


# --- AC3: a withdrawal is a new row --------------------------------------

def test_withdrawal_appends_a_new_row_and_leaves_the_old_one_alone(audited):
    old = _grant(llm_choice="anthropic", consent_version="1.0", consent_text_hash="a" * 64)
    db = _FakeDB([], [old])

    outcome = _withdraw(db, ["auto_apply"])

    assert db.added == [outcome.record] and db.commits == 1
    new = outcome.record
    assert new is not old and new.event == "withdrawn"
    assert (new.consented_to_auto_apply, new.consented_to_llm_processing,
            new.consented_to_data_processing) == (False, True, True)
    assert (new.user_id, new.llm_choice, new.consent_version, new.consent_text_hash) == (
        "u1", "anthropic", "1.0", "a" * 64)
    assert (new.ip_address, new.user_agent) == ("203.0.113.9", "Browser/2")
    assert outcome.withdrawn == ("auto_apply",)
    assert old.consented_to_auto_apply is True and old.event == "granted"
    assert old.ip_address == "198.51.100.1"


def test_withdrawal_carries_scopes_already_withdrawn_earlier(audited):
    latest = _grant(event="withdrawn", consented_to_auto_apply=False)
    outcome = _withdraw(_FakeDB([], [latest]), ["llm_processing", "data_processing"])

    new = outcome.record
    assert (new.consented_to_auto_apply, new.consented_to_llm_processing,
            new.consented_to_data_processing) == (False, False, False)
    assert outcome.withdrawn == ("data_processing", "llm_processing")


def test_withdrawal_stamps_its_own_time():
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    outcome = _withdraw(_FakeDB([], [_grant()]), ["auto_apply"])
    assert outcome.record.consented_at >= before


# --- AC4: audit without network identifiers --------------------------------

def test_withdrawal_is_audited_with_user_and_scopes_only(audited):
    _withdraw(_FakeDB([], [_grant()]), ["llm_processing", "auto_apply", "auto_apply"])

    assert audited == [("consent.withdrawn", {
        "user_id": "u1", "details": {"scopes": ["auto_apply", "llm_processing"]},
    })]
    assert "203.0.113.9" not in repr(audited) and "Browser/2" not in repr(audited)


# --- AC5: idempotent and serialised --------------------------------------

def test_withdrawing_an_already_withdrawn_scope_writes_nothing(audited):
    latest = _grant(event="withdrawn", consented_to_auto_apply=False)
    db = _FakeDB([], [latest])

    outcome = _withdraw(db, ["auto_apply"])

    assert outcome.record is latest and outcome.withdrawn == ()
    assert db.added == [] and db.commits == 0 and audited == []


def test_withdrawal_locks_the_user_row_before_reading_consent(audited):
    db = _FakeDB([], [_grant()])
    _withdraw(db, ["auto_apply"])

    lock, read = db.statements
    assert lock.startswith("SELECT users.id") and lock.endswith("FOR UPDATE")
    assert "users.id = %(id_1)s" in lock
    assert "FROM consent_records" in read


def test_withdrawal_without_consent_on_record_is_refused(audited):
    db = _FakeDB([], [])
    with pytest.raises(NoConsentOnRecord):
        _withdraw(db, ["auto_apply"])
    assert db.added == [] and audited == []


def test_unknown_scope_is_rejected_before_touching_the_database():
    db = _FakeDB()
    with pytest.raises(ValueError, match="marketing"):
        _withdraw(db, ["auto_apply", "marketing"])
    with pytest.raises(ValueError):
        _withdraw(db, [])
    assert db.statements == []


# --- AC11: every check needs data_processing too; no record means no -------

def test_scopes_are_exactly_the_three_consents():
    assert set(CONSENT_SCOPES) == {"auto_apply", "llm_processing", "data_processing"}


@pytest.mark.parametrize("scope", ["auto_apply", "llm_processing", "data_processing"])
def test_full_consent_allows_every_scope(scope):
    assert consent_allows(_grant(), scope) is True


@pytest.mark.parametrize("scope,column", [
    ("auto_apply", "consented_to_auto_apply"),
    ("llm_processing", "consented_to_llm_processing"),
])
def test_a_withdrawn_scope_is_not_allowed_but_the_others_are(scope, column):
    record = _grant(**{column: False})
    assert consent_allows(record, scope) is False
    other = ({"auto_apply", "llm_processing"} - {scope}).pop()
    assert consent_allows(record, other) is True


@pytest.mark.parametrize("scope", ["auto_apply", "llm_processing", "data_processing"])
def test_withdrawn_data_processing_stops_every_scope(scope):
    assert consent_allows(_grant(consented_to_data_processing=False), scope) is False


@pytest.mark.parametrize("scope", ["auto_apply", "llm_processing", "data_processing"])
def test_no_consent_record_allows_nothing(scope):
    assert consent_allows(None, scope) is False
