"""
PII field classification policy.

ENCRYPTED  — Fernet-encrypted at rest; decrypted only in application memory
HASHED     — one-way SHA-256; used as lookup key only
PLAIN      — not PII or non-sensitive enough to store plaintext
"""

ENCRYPTED_FIELDS = {
    "email",
    "phone",
    "full_name",
    "portal_session_cookies",
    "portal_password_temp",
    "work_history_salary",
    "system_portal_credentials",
}

HASHED_FIELDS = {
    "email_hash",
    "thumbprint",
}

PLAIN_FIELDS = {
    "city",
    "current_role",
    "years_experience",
    "skills",
    "desired_roles",
    "preferred_locations",
    "oauth_provider",
    "oauth_sub",
    "notification_platform",
    "llm_choice",
    "match_threshold",
    "apply_cap_daily",
    "status_check_frequency_hours",
    "auto_apply_enabled",
    "hitl_enabled",
    "wfh_preference",
    "notice_period_days",
    "salary_min_lpa",
}
