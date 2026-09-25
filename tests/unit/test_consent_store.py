"""
R11: DPDPA consent capture is the legally load-bearing record.
Given a user completing sign-up, when consent is recorded, then an immutable
ConsentRecord is persisted with the exact consents, version and a hash of the
text shown, and an audit entry is written for the grant.
"""
import asyncio
from hashlib import sha256

import pytest

from app.compliance import consent_store
from app.compliance.consent_store import (
    CONSENT_TEXT,
    CURRENT_CONSENT_VERSION,
    record_consent,
)
from app.compliance.dpdpa import ConsentRecord


class _FakeDB:
    def __init__(self):
        self.added, self.commits = [], 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def audited(monkeypatch):
    calls = []
    monkeypatch.setattr(consent_store, "audit", lambda event, **kw: calls.append((event, kw)))
    return calls


def _record(db, auto_apply=True, llm=False):
    return asyncio.run(record_consent(
        user_id="u1", ip_address="203.0.113.7", user_agent="UA/1.0",
        consented_to_auto_apply=auto_apply, consented_to_llm_processing=llm,
        llm_choice="claude", db=db,
    ))


def test_record_consent_persists_exact_consents(audited):
    db = _FakeDB()
    record = _record(db, auto_apply=True, llm=False)

    assert isinstance(record, ConsentRecord)
    assert db.added == [record] and db.commits == 1
    assert (record.user_id, record.ip_address, record.user_agent) == ("u1", "203.0.113.7", "UA/1.0")
    assert record.consented_to_data_processing is True
    assert record.consented_to_auto_apply is True
    assert record.consented_to_llm_processing is False
    assert record.llm_choice == "claude"
    assert record.consent_version == CURRENT_CONSENT_VERSION
    assert record.consent_text_hash == sha256(CONSENT_TEXT.encode()).hexdigest()


def test_record_consent_writes_a_grant_audit_entry(audited):
    _record(_FakeDB(), auto_apply=False, llm=True)
    assert audited == [("consent.granted", {
        "user_id": "u1",
        "details": {
            "consent_version": CURRENT_CONSENT_VERSION,
            "consented_to_auto_apply": False,
            "consented_to_llm_processing": True,
            "llm_choice": "claude",
        },
    })]


def test_audit_entry_carries_no_network_identifiers(audited):
    _record(_FakeDB())
    _, kwargs = audited[0]
    assert "203.0.113.7" not in repr(kwargs) and "UA/1.0" not in repr(kwargs)
