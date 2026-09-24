"""
R6: the PII classification policy is enforced, not just documented.
Given every mapped column in the shared and tenant schemas, when a column's name
marks it as personal data, then it must be stored encrypted (``*_encrypted``) or
hashed, or carry a reviewed plaintext exception. Adding e.g. a plain ``phone``
column fails this test.
"""
import importlib
import pkgutil

import pytest

import app.models
import app.tenant_models
from app.database import Base
from app.security import pii_policy
from app.security.pii_policy import KNOWN_VIOLATIONS, unprotected_pii_columns
from app.tenant_models.profile import TenantBase


def _all_columns() -> list[tuple[str, str]]:
    for pkg in (app.models, app.tenant_models):
        for mod in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"{pkg.__name__}.{mod.name}")
    importlib.import_module("app.compliance.dpdpa")
    return [
        (table.name, column.name)
        for metadata in (Base.metadata, TenantBase.metadata)
        for table in metadata.sorted_tables
        for column in table.columns
    ]


def test_no_model_column_stores_pii_in_plaintext():
    violations = set(unprotected_pii_columns(_all_columns()))
    new = violations - KNOWN_VIOLATIONS
    assert new == set(), f"PII columns must be *_encrypted or hashed: {sorted(new)}"


def test_known_violations_still_exist():
    """A fixed violation must be removed from KNOWN_VIOLATIONS so it cannot regress."""
    stale = KNOWN_VIOLATIONS - set(unprotected_pii_columns(_all_columns()))
    assert stale == set(), f"remove fixed entries from KNOWN_VIOLATIONS: {sorted(stale)}"


@pytest.mark.parametrize("column", [
    "email", "phone", "full_name", "mobile_phone", "password", "session_cookies",
    "api_secret", "portal_credentials", "aadhaar_number", "pan_number", "dob", "home_address",
])
def test_plaintext_pii_names_are_flagged(column):
    assert unprotected_pii_columns([("t", column)]) == [("t", column)]


@pytest.mark.parametrize("column", [
    "email_encrypted", "phone_encrypted", "email_hash", "hashed_password", "thumbprint",
    "skill_name", "city", "salary_min_lpa",
])
def test_protected_or_non_pii_names_pass(column):
    assert unprotected_pii_columns([("t", column)]) == []


def test_reviewed_plaintext_exception_passes_only_for_its_table():
    table, column = next(iter(pii_policy.PLAINTEXT_EXCEPTIONS))
    assert unprotected_pii_columns([(table, column)]) == []
    assert unprotected_pii_columns([("other_table", column)]) == [("other_table", column)]


def test_policy_classes_are_disjoint():
    e, h, p = pii_policy.ENCRYPTED_FIELDS, pii_policy.HASHED_FIELDS, pii_policy.PLAIN_FIELDS
    assert not (e & h or e & p or h & p)
