"""Pins the shared-schema (public) models to an explicit column contract.

Every mutation of a literal in app/models/*.py (nullable, index, unique,
default, server_default, enum member value, ...) must flip at least one
assertion below. Values were read directly off the current model source,
not re-derived from the models themselves, so a mutation has nothing to
hide behind.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base
from app.models.admin import AdminRole, AdminUser
from app.models.job import Job
from app.models.portal_account import (
    PortalAccountHealth,
    PortalName,
    SystemPortalAccount,
)
from app.models.skill_taxonomy import SkillTaxonomy, TaxonomySource, TaxonomyStatus
from app.models.user import OAuthProvider, User, UserTier

_NO_DEFAULT = object()
_UUID = object()
_UTC_NOW = object()
_EMPTY_LIST = object()
_EMPTY_DICT = object()


def _resolve(default_obj):
    if default_obj is None:
        return _NO_DEFAULT
    if default_obj.is_scalar:
        return default_obj.arg
    return default_obj.arg(None)


def _assert_default_like(default_obj, expected, label):
    resolved = _resolve(default_obj)
    if expected is _NO_DEFAULT:
        assert resolved is _NO_DEFAULT, f"{label}: expected none, got {resolved!r}"
    elif expected is _UUID:
        assert isinstance(resolved, str), f"{label}: expected uuid string, got {resolved!r}"
        uuid.UUID(resolved)
    elif expected is _UTC_NOW:
        assert isinstance(resolved, datetime) and resolved.tzinfo is not None, label
    elif expected is _EMPTY_LIST:
        assert resolved == [], f"{label}: expected [], got {resolved!r}"
    elif expected is _EMPTY_DICT:
        assert resolved == {}, f"{label}: expected {{}}, got {resolved!r}"
    else:
        assert resolved == expected, f"{label}: expected {expected!r}, got {resolved!r}"


def _check_type(col, label, *, type_, length, tz, enum_class, enum_name):
    assert isinstance(col.type, type_), f"{label}: type {col.type!r} is not {type_}"
    if length is not None:
        assert col.type.length == length, f"{label}: length {col.type.length} != {length}"
    if tz is not None:
        assert col.type.timezone is tz, f"{label}: timezone {col.type.timezone} != {tz}"
    if enum_class is not None:
        assert col.type.enum_class is enum_class, f"{label}: enum_class mismatch"
    if enum_name is not None:
        assert col.type.name == enum_name, f"{label}: enum type name mismatch"


def _check_shape(col, label, *, nullable, primary_key, index, unique):
    assert col.nullable is nullable, f"{label}: nullable {col.nullable} != {nullable}"
    assert col.primary_key is primary_key, f"{label}: primary_key {col.primary_key} != {primary_key}"
    assert col.index is index, f"{label}: index {col.index} != {index}"
    assert col.unique is unique, f"{label}: unique {col.unique} != {unique}"


def _check_defaults(col, label, *, default, onupdate, server_default):
    _assert_default_like(col.default, default, f"{label} default")
    _assert_default_like(col.onupdate, onupdate, f"{label} onupdate")
    sd = col.server_default.arg if col.server_default is not None else None
    assert sd == server_default, f"{label}: server_default {sd!r} != {server_default!r}"


def _check_column(
    table,
    name,
    *,
    type_,
    nullable,
    primary_key=False,
    index=None,
    unique=None,
    length=None,
    tz=None,
    default=_NO_DEFAULT,
    onupdate=_NO_DEFAULT,
    server_default=None,
    enum_class=None,
    enum_name=None,
):
    col = table.columns[name]
    label = f"{table.name}.{name}"
    _check_type(col, label, type_=type_, length=length, tz=tz, enum_class=enum_class, enum_name=enum_name)
    _check_shape(col, label, nullable=nullable, primary_key=primary_key, index=index, unique=unique)
    _check_defaults(col, label, default=default, onupdate=onupdate, server_default=server_default)


def _unique_constraint_names(table):
    return {c.name for c in table.constraints if isinstance(c, UniqueConstraint)}


def _enum_members(enum_cls):
    return {m.name: m.value for m in enum_cls}


def test_shared_models_are_registered_on_the_shared_base():
    assert AdminUser.metadata is Base.metadata
    assert Job.metadata is Base.metadata
    assert SystemPortalAccount.metadata is Base.metadata
    assert SkillTaxonomy.metadata is Base.metadata
    assert User.metadata is Base.metadata


def test_admin_role_enum_members():
    assert _enum_members(AdminRole) == {
        "super_admin": "super_admin",
        "ops_admin": "ops_admin",
        "content_admin": "content_admin",
        "support_admin": "support_admin",
    }


def test_admin_user_table_args_and_columns():
    t = AdminUser.__table__
    assert _unique_constraint_names(t) == {"uq_admin_users_email_hash"}
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "email_hash", type_=String, length=64, nullable=False, index=True)
    _check_column(t, "email_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "full_name_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "hashed_password", type_=String, length=128, nullable=False)
    _check_column(
        t, "role", type_=SAEnum, nullable=False,
        enum_class=AdminRole, enum_name="admin_role_enum", default=AdminRole.support_admin,
    )
    _check_column(t, "totp_secret_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "totp_verified", type_=Boolean, nullable=False, default=False)
    _check_column(t, "is_active", type_=Boolean, nullable=False, default=True)
    _check_column(t, "created_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)
    _check_column(t, "last_login", type_=DateTime, tz=True, nullable=True)


def test_job_table_args_and_columns():
    t = Job.__table__
    assert _unique_constraint_names(t) == {"uq_job_portal_id"}
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "portal", type_=String, length=32, nullable=False, index=True)
    _check_column(t, "portal_job_id", type_=String, length=256, nullable=False, index=True)
    _check_column(t, "title", type_=String, length=512, nullable=False)
    _check_column(t, "company", type_=String, length=256, nullable=False, index=True)
    _check_column(t, "location", type_=String, length=256, nullable=False)
    _check_column(t, "job_url", type_=String, length=1024, nullable=False)
    _check_column(t, "description", type_=Text, nullable=False, default="")
    _check_column(t, "skills_required", type_=JSONB, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "salary_range", type_=String, length=256, nullable=False, default="")
    _check_column(t, "experience_required", type_=String, length=128, nullable=False, default="")
    _check_column(t, "is_easy_apply", type_=Boolean, nullable=False, default=False)
    _check_column(t, "is_active", type_=Boolean, nullable=False, index=True, default=True)
    _check_column(t, "extra", type_=JSONB, nullable=False, default=_EMPTY_DICT)
    _check_column(t, "posted_at", type_=DateTime, tz=True, nullable=True)
    _check_column(t, "crawled_at", type_=DateTime, tz=True, nullable=False, index=True, default=_UTC_NOW)
    _check_column(
        t, "last_seen_at", type_=DateTime, tz=True, nullable=False,
        default=_UTC_NOW, onupdate=_UTC_NOW,
    )


def test_portal_name_and_health_enum_members():
    assert _enum_members(PortalName) == {
        "naukri": "naukri",
        "linkedin": "linkedin",
        "glassdoor": "glassdoor",
        "indeed": "indeed",
        "monster": "monster",
        "shine": "shine",
    }
    assert _enum_members(PortalAccountHealth) == {
        "healthy": "healthy",
        "degraded": "degraded",
        "blocked": "blocked",
        "unknown": "unknown",
    }


def test_system_portal_account_columns():
    t = SystemPortalAccount.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(
        t, "portal", type_=SAEnum, nullable=False, unique=True,
        enum_class=PortalName, enum_name="portal_name_enum",
    )
    _check_column(t, "email_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "password_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "session_cookies_encrypted", type_=LargeBinary, nullable=True)
    _check_column(t, "session_expires_at", type_=DateTime, tz=True, nullable=True)
    _check_column(
        t, "health", type_=SAEnum, nullable=False,
        enum_class=PortalAccountHealth, enum_name="portal_account_health_enum",
        default=PortalAccountHealth.unknown,
    )
    _check_column(t, "last_login", type_=DateTime, tz=True, nullable=True)
    _check_column(t, "last_crawl", type_=DateTime, tz=True, nullable=True)
    _check_column(t, "notes", type_=Text, nullable=True)
    _check_column(t, "is_active", type_=Boolean, nullable=False, default=True)
    _check_column(t, "created_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_taxonomy_status_and_source_enum_members():
    assert _enum_members(TaxonomyStatus) == {
        "active": "active",
        "pending_review": "pending_review",
        "rejected": "rejected",
    }
    assert _enum_members(TaxonomySource) == {
        "esco": "esco",
        "onet": "onet",
        "dynamic_discovery": "dynamic_discovery",
        "manual": "manual",
    }


def test_skill_taxonomy_table_args_and_columns():
    t = SkillTaxonomy.__table__
    assert _unique_constraint_names(t) == {"uq_skill_taxonomy_skill_name"}
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "skill_name", type_=String, length=256, nullable=False, index=True)
    _check_column(t, "category", type_=String, length=128, nullable=False)
    _check_column(t, "subcategory", type_=String, length=128, nullable=True)
    _check_column(
        t, "source", type_=SAEnum, nullable=False,
        enum_class=TaxonomySource, enum_name="taxonomy_source_enum",
    )
    _check_column(
        t, "status", type_=SAEnum, nullable=False,
        enum_class=TaxonomyStatus, enum_name="taxonomy_status_enum",
        default=TaxonomyStatus.active,
    )
    _check_column(t, "auto_suggested_category", type_=String, length=128, nullable=True)
    _check_column(t, "description", type_=Text, nullable=True)
    _check_column(t, "esco_uri", type_=String, length=512, nullable=True)
    _check_column(t, "onet_code", type_=String, length=32, nullable=True)
    _check_column(t, "added_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_oauth_provider_and_user_tier_enum_members():
    assert _enum_members(OAuthProvider) == {
        "google": "google",
        "linkedin": "linkedin",
        "facebook": "facebook",
        "microsoft": "microsoft",
    }
    assert _enum_members(UserTier) == {"free": "free", "pro": "pro", "enterprise": "enterprise"}


def test_user_table_unique_constraints_and_identity_columns():
    t = User.__table__
    assert _unique_constraint_names(t) == {
        "uq_users_email_hash",
        "uq_users_thumbprint",
        "uq_users_schema_name",
    }
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "email_hash", type_=String, length=64, nullable=False, index=True)
    _check_column(t, "email_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "thumbprint", type_=String, length=64, nullable=False, index=True)
    _check_column(t, "schema_name", type_=String, length=70, nullable=False)
    _check_column(
        t, "oauth_provider", type_=SAEnum, nullable=False,
        enum_class=OAuthProvider, enum_name="oauth_provider_enum",
    )
    _check_column(t, "oauth_sub", type_=String, length=256, nullable=False)


def test_user_table_totp_and_state_columns():
    t = User.__table__
    _check_column(t, "totp_secret_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "totp_verified", type_=Boolean, nullable=False, default=False)
    _check_column(
        t, "totp_failed_attempts", type_=Integer, nullable=False,
        default=0, server_default="0",
    )
    _check_column(t, "totp_locked_until", type_=DateTime, tz=True, nullable=True)
    _check_column(t, "totp_last_used_step", type_=BigInteger, nullable=True)
    _check_column(t, "is_active", type_=Boolean, nullable=False, default=True)
    _check_column(t, "onboarding_complete", type_=Boolean, nullable=False, default=False)
    _check_column(t, "onboarding_step", type_=Integer, nullable=False, default=1)
    _check_column(
        t, "tier", type_=SAEnum, nullable=False,
        enum_class=UserTier, enum_name="user_tier_enum", default=UserTier.free,
    )


def test_user_table_timestamp_columns():
    t = User.__table__
    _check_column(t, "created_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)
    _check_column(
        t, "updated_at", type_=DateTime, tz=True, nullable=False,
        default=_UTC_NOW, onupdate=_UTC_NOW,
    )
    _check_column(t, "scheduled_deletion_at", type_=DateTime, tz=True, nullable=True)
