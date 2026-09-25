"""
CHG-007 AC1: a consent record says whether it grants or withdraws consent.
Rows are append-only, so the event is set once, when the row is written.
"""
from app.compliance.dpdpa import ConsentRecord


def test_consent_record_event_column_is_required_and_defaults_to_granted():
    col = ConsentRecord.__table__.columns["event"]
    assert col.nullable is False and col.type.length == 16
    assert col.default.arg == "granted" and col.server_default.arg == "granted"
