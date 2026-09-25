"""Pins the per-user-schema (tenant) models to an explicit column contract.

Every mutation of a literal in app/tenant_models/*.py (nullable, index,
unique, default, enum member value, ...) must flip at least one assertion
below. Values were read directly off the current model source, not
re-derived from the models themselves, so a mutation has nothing to hide
behind.
"""
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum, Float, Integer, LargeBinary, String, Text

from app.tenant_models.application import (
    ApplicationFailureReason,
    ApplicationStatus,
    ApplicationStatusLog,
    JobApplication,
)
from app.tenant_models.job import MatchedJob
from app.tenant_models.ml_feedback import MLFeedback, OutcomeSignal
from app.tenant_models.notification import NotificationChannel, NotificationLog
from app.tenant_models.profile import (
    LLMChoice,
    NotificationPlatform,
    StatusCheckFrequency,
    TenantBase,
    UserPreferences,
    UserProfile,
    WFHPreference,
)
from app.tenant_models.resume import MasterResume, TailoredResume
from app.tenant_models.screening_qa import MissingInfoLog, PortalScreeningAnswer
from app.tenant_models.skill import SkillMatchCache, UserSkill

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


def _enum_members(enum_cls):
    return {m.name: m.value for m in enum_cls}


def test_tenant_models_are_registered_on_the_tenant_base_not_shared_base():
    assert JobApplication.metadata is TenantBase.metadata
    assert ApplicationStatusLog.metadata is TenantBase.metadata
    assert MatchedJob.metadata is TenantBase.metadata
    assert MLFeedback.metadata is TenantBase.metadata
    assert NotificationLog.metadata is TenantBase.metadata
    assert UserProfile.metadata is TenantBase.metadata
    assert UserPreferences.metadata is TenantBase.metadata
    assert MasterResume.metadata is TenantBase.metadata
    assert TailoredResume.metadata is TenantBase.metadata
    assert PortalScreeningAnswer.metadata is TenantBase.metadata
    assert MissingInfoLog.metadata is TenantBase.metadata
    assert UserSkill.metadata is TenantBase.metadata
    assert SkillMatchCache.metadata is TenantBase.metadata


def test_application_status_and_failure_reason_enum_members():
    assert _enum_members(ApplicationStatus) == {
        "pending_hitl": "pending_hitl",
        "applying": "applying",
        "applied": "applied",
        "viewed": "viewed",
        "shortlisted": "shortlisted",
        "interview_scheduled": "interview_scheduled",
        "rejected": "rejected",
        "withdrawn": "withdrawn",
        "failed_portal_error": "failed_portal_error",
        "failed_low_match": "failed_low_match",
        "failed_missing_info": "failed_missing_info",
    }
    assert _enum_members(ApplicationFailureReason) == {
        "portal_rejected": "portal_rejected",
        "low_match_score": "low_match_score",
        "missing_profile_info": "missing_profile_info",
        "session_expired": "session_expired",
        "unknown": "unknown",
    }


def test_job_application_columns():
    t = JobApplication.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "matched_job_id", type_=String, length=36, nullable=False, index=True)
    _check_column(t, "portal", type_=String, length=32, nullable=False)
    _check_column(t, "portal_job_id", type_=String, length=256, nullable=False)
    _check_column(t, "portal_application_id", type_=String, length=256, nullable=True)
    _check_column(t, "job_title", type_=String, length=512, nullable=False)
    _check_column(t, "company", type_=String, length=256, nullable=False)
    _check_column(t, "match_score", type_=Float, nullable=False)
    _check_column(
        t, "status", type_=SAEnum, nullable=False,
        enum_class=ApplicationStatus, enum_name="app_status_enum",
        default=ApplicationStatus.applying,
    )
    _check_column(
        t, "failure_reason", type_=SAEnum, nullable=True,
        enum_class=ApplicationFailureReason, enum_name="app_failure_reason_enum",
    )
    _check_column(t, "failure_detail", type_=Text, nullable=True)
    _check_column(t, "tailored_resume_id", type_=String, length=36, nullable=True)
    _check_column(t, "applied_at", type_=DateTime, tz=True, nullable=True)
    _check_column(t, "last_status_check", type_=DateTime, tz=True, nullable=True)
    _check_column(t, "created_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_application_status_log_columns():
    t = ApplicationStatusLog.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "application_id", type_=String, length=36, nullable=False, index=True)
    _check_column(t, "from_status", type_=String, length=64, nullable=True)
    _check_column(t, "to_status", type_=String, length=64, nullable=False)
    _check_column(t, "note", type_=Text, nullable=True)
    _check_column(t, "recorded_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_matched_job_columns():
    t = MatchedJob.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "portal", type_=String, length=32, nullable=False, index=True)
    _check_column(t, "portal_job_id", type_=String, length=256, nullable=False)
    _check_column(t, "title", type_=String, length=512, nullable=False)
    _check_column(t, "company", type_=String, length=256, nullable=False)
    _check_column(t, "location", type_=String, length=256, nullable=False)
    _check_column(t, "job_url", type_=String, length=1024, nullable=False)
    _check_column(t, "description_snippet", type_=Text, nullable=True)
    _check_column(t, "match_score", type_=Float, nullable=False)
    _check_column(t, "explainability", type_=JSON, nullable=False, default=_EMPTY_DICT)
    _check_column(t, "is_active", type_=Boolean, nullable=False, default=True)
    _check_column(t, "discovered_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_ml_feedback_outcome_signal_enum_members_and_columns():
    assert _enum_members(OutcomeSignal) == {
        "interview_scheduled": "interview_scheduled",
        "offer_received": "offer_received",
        "rejected_by_recruiter": "rejected_by_recruiter",
        "no_response": "no_response",
        "withdrawn_by_user": "withdrawn_by_user",
    }
    t = MLFeedback.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "application_id", type_=String, length=36, nullable=False, index=True)
    _check_column(t, "portal", type_=String, length=32, nullable=False)
    _check_column(t, "job_title", type_=String, length=512, nullable=False)
    _check_column(t, "match_score_at_apply", type_=Float, nullable=False)
    _check_column(
        t, "outcome", type_=SAEnum, nullable=False,
        enum_class=OutcomeSignal, enum_name="outcome_signal_enum",
    )
    _check_column(t, "recorded_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_notification_channel_enum_members_and_log_columns():
    assert _enum_members(NotificationChannel) == {
        "in_app": "in_app",
        "email": "email",
        "telegram": "telegram",
        "discord": "discord",
    }
    t = NotificationLog.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "event_type", type_=String, length=64, nullable=False)
    _check_column(
        t, "channel", type_=SAEnum, nullable=False,
        enum_class=NotificationChannel, enum_name="notif_channel_enum",
    )
    _check_column(t, "subject", type_=String, length=512, nullable=True)
    _check_column(t, "body_snippet", type_=Text, nullable=True)
    _check_column(t, "delivered", type_=Boolean, nullable=False, default=False)
    _check_column(t, "read", type_=Boolean, nullable=False, default=False)
    _check_column(t, "sent_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_profile_enum_members():
    assert _enum_members(WFHPreference) == {
        "onsite": "onsite", "hybrid": "hybrid", "remote": "remote", "any": "any",
    }
    assert _enum_members(LLMChoice) == {"self_hosted": "self_hosted", "api": "api"}
    assert _enum_members(NotificationPlatform) == {"telegram": "telegram", "discord": "discord"}
    assert _enum_members(StatusCheckFrequency) == {
        "every_6h": 6, "every_12h": 12, "every_18h": 18, "every_24h": 24,
    }


def test_user_profile_columns():
    t = UserProfile.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "full_name_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "phone_encrypted", type_=LargeBinary, nullable=False)
    _check_column(t, "city", type_=String, length=128, nullable=False)
    _check_column(t, "state", type_=String, length=128, nullable=False)
    _check_column(t, "current_role", type_=String, length=256, nullable=False)
    _check_column(t, "years_experience", type_=Integer, nullable=False)
    _check_column(t, "work_history", type_=JSON, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "education", type_=JSON, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "avatar_url", type_=String, length=512, nullable=True)
    _check_column(
        t, "updated_at", type_=DateTime, tz=True, nullable=False,
        default=_UTC_NOW, onupdate=_UTC_NOW,
    )


def test_user_preferences_columns_scalars_and_flags():
    t = UserPreferences.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "desired_roles", type_=JSON, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "preferred_locations", type_=JSON, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "salary_min_lpa", type_=Integer, nullable=True)
    _check_column(t, "notice_period_days", type_=Integer, nullable=False, default=0)
    _check_column(t, "telegram_chat_id", type_=String, length=64, nullable=True)
    _check_column(t, "discord_channel_id", type_=String, length=64, nullable=True)
    _check_column(t, "auto_apply_enabled", type_=Boolean, nullable=False, default=True)
    _check_column(t, "hitl_enabled", type_=Boolean, nullable=False, default=False)
    _check_column(t, "match_threshold", type_=Float, nullable=False, default=0.7)
    _check_column(t, "apply_cap_daily", type_=Integer, nullable=False, default=20)
    _check_column(t, "status_check_frequency_hours", type_=Integer, nullable=False, default=24)


def test_user_preferences_columns_enums_lists_and_timestamps():
    t = UserPreferences.__table__
    _check_column(
        t, "wfh_preference", type_=SAEnum, nullable=False,
        enum_class=WFHPreference, enum_name="wfh_pref_enum", default=WFHPreference.any,
    )
    _check_column(
        t, "llm_choice", type_=SAEnum, nullable=False,
        enum_class=LLMChoice, enum_name="llm_choice_enum", default=LLMChoice.self_hosted,
    )
    _check_column(
        t, "notification_platform", type_=SAEnum, nullable=False,
        enum_class=NotificationPlatform, enum_name="notif_platform_enum",
        default=NotificationPlatform.telegram,
    )
    _check_column(t, "portal_apply_caps", type_=JSON, nullable=False, default=_EMPTY_DICT)
    _check_column(t, "company_blacklist", type_=JSON, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "title_blacklist", type_=JSON, nullable=False, default=_EMPTY_LIST)
    _check_column(t, "auto_apply_paused", type_=Boolean, nullable=False, default=False)
    _check_column(t, "pause_until", type_=DateTime, tz=True, nullable=True)
    _check_column(
        t, "updated_at", type_=DateTime, tz=True, nullable=False,
        default=_UTC_NOW, onupdate=_UTC_NOW,
    )


def test_master_and_tailored_resume_columns():
    t = MasterResume.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "minio_key", type_=String, length=512, nullable=False)
    _check_column(t, "original_filename", type_=String, length=256, nullable=False)
    _check_column(t, "uploaded_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)
    _check_column(t, "is_active", type_=Boolean, nullable=False, default=True)

    tt = TailoredResume.__table__
    _check_column(tt, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(tt, "job_id", type_=String, length=36, nullable=False, index=True)
    _check_column(tt, "minio_key", type_=String, length=512, nullable=False)
    _check_column(tt, "llm_choice_used", type_=String, length=32, nullable=False)
    _check_column(tt, "generated_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)
    _check_column(tt, "purged", type_=Boolean, nullable=False, default=False)


def test_portal_screening_answer_columns():
    t = PortalScreeningAnswer.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "portal", type_=String, length=32, nullable=False, index=True)
    _check_column(t, "question_fingerprint", type_=String, length=64, nullable=False, index=True)
    _check_column(t, "question_text", type_=Text, nullable=False)
    _check_column(t, "answer_text", type_=Text, nullable=False)
    _check_column(t, "auto_generated", type_=Boolean, nullable=False, default=True)
    _check_column(t, "user_verified", type_=Boolean, nullable=False, default=False)
    _check_column(t, "created_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)


def test_missing_info_log_columns():
    t = MissingInfoLog.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "portal", type_=String, length=32, nullable=False)
    _check_column(t, "field_name", type_=String, length=128, nullable=False)
    _check_column(t, "field_label", type_=String, length=256, nullable=False)
    _check_column(t, "encountered_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)
    _check_column(t, "resolved", type_=Boolean, nullable=False, default=False)
    _check_column(t, "resolved_at", type_=DateTime, tz=True, nullable=True)


def test_user_skill_and_skill_match_cache_columns():
    t = UserSkill.__table__
    _check_column(t, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(t, "skill_name", type_=String, length=256, nullable=False, index=True)
    _check_column(t, "taxonomy_id", type_=String, length=64, nullable=True)
    _check_column(t, "proficiency", type_=String, length=32, nullable=False, default="intermediate")
    _check_column(t, "years_used", type_=Float, nullable=True)
    _check_column(t, "added_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)

    tt = SkillMatchCache.__table__
    _check_column(tt, "id", type_=String, length=36, nullable=False, primary_key=True, default=_UUID)
    _check_column(tt, "tfidf_vector", type_=JSON, nullable=False)
    _check_column(tt, "built_at", type_=DateTime, tz=True, nullable=False, default=_UTC_NOW)
