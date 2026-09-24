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

# Column-name tokens that mark a column as personal data or a secret.
PII_NAME_TOKENS = {
    "email", "phone", "mobile", "password", "cookie", "cookies", "secret",
    "credential", "credentials", "aadhaar", "pan", "dob", "address",
}

# (table, column) stored in plaintext by reviewed decision.
PLAINTEXT_EXCEPTIONS = {
    ("consent_records", "ip_address"): "DPDPA consent evidence; must be readable",
}

# Plaintext PII awaiting a fix. Listed so they cannot spread; remove when fixed.
KNOWN_VIOLATIONS = {
    ("users", "totp_secret"),
    ("admin_users", "totp_secret"),
}


def _is_protected(column: str) -> bool:
    return (
        column.endswith(("_encrypted", "_hash"))
        or column.startswith("hashed_")
        or column in HASHED_FIELDS
    )


def _looks_like_pii(column: str) -> bool:
    return "full_name" in column or bool(PII_NAME_TOKENS & set(column.split("_")))


def unprotected_pii_columns(columns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return (table, column) pairs that look like PII but are neither encrypted,
    hashed, nor a reviewed plaintext exception."""
    return [
        (table, column) for table, column in columns
        if _looks_like_pii(column)
        and not _is_protected(column)
        and (table, column) not in PLAINTEXT_EXCEPTIONS
    ]
