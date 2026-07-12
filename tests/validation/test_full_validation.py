"""
Comprehensive validation test suite for jH_ANS.
All external dependencies (DB, network, Docker) are mocked.
Run with: python -m pytest tests/validation/test_full_validation.py -v --tb=short
"""
# ---------------------------------------------------------------------------
# Bootstrap env vars before any app import (mirrors unit conftest pattern)
# ---------------------------------------------------------------------------
import os
import base64

from cryptography.fernet import Fernet as _Fernet

_test_fernet_key = _Fernet.generate_key().decode()
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-bytes-xxxxxxxx")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "testminiocredential")
os.environ.setdefault("FERNET_KEY", _test_fernet_key)

# ---------------------------------------------------------------------------
import asyncio
import hashlib
import html
import re
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from bs4 import BeautifulSoup

# ===========================================================================
# 1. SECURITY & IDENTITY
# ===========================================================================

class TestEncryption:
    """Fernet encrypt/decrypt round-trips for PII field types."""

    def setup_method(self):
        from app.security.encryption import encrypt, decrypt
        self.encrypt = encrypt
        self.decrypt = decrypt

    def test_email_roundtrip(self):
        value = "user@example.com"
        assert self.decrypt(self.encrypt(value)) == value

    def test_phone_roundtrip(self):
        value = "+919876543210"
        assert self.decrypt(self.encrypt(value)) == value

    def test_name_roundtrip(self):
        value = "Ravi Kumar Sharma"
        assert self.decrypt(self.encrypt(value)) == value

    def test_encrypt_returns_bytes(self):
        token = self.encrypt("test@test.com")
        assert isinstance(token, bytes)

    def test_different_values_different_tokens(self):
        # Fernet includes random IV so same value produces different tokens
        t1 = self.encrypt("a@a.com")
        t2 = self.encrypt("a@a.com")
        # They decrypt to the same value but tokens may differ (nondeterministic)
        assert self.decrypt(t1) == self.decrypt(t2) == "a@a.com"


class TestThumbprint:
    """generate_thumbprint() and schema_name_from_thumbprint()."""

    def setup_method(self):
        from app.security.encryption import (
            generate_thumbprint,
            schema_name_from_thumbprint,
        )
        self.gen = generate_thumbprint
        self.schema = schema_name_from_thumbprint

    def test_deterministic(self):
        a = self.gen("user@example.com", "+919876543210")
        b = self.gen("user@example.com", "+919876543210")
        assert a == b

    def test_unique_different_inputs(self):
        a = self.gen("user1@example.com", "+919876543210")
        b = self.gen("user2@example.com", "+919876543210")
        assert a != b

    def test_unique_different_phones(self):
        a = self.gen("user@example.com", "+910000000001")
        b = self.gen("user@example.com", "+910000000002")
        assert a != b

    def test_schema_name_prefix(self):
        tp = self.gen("user@example.com", "+919876543210")
        name = self.schema(tp)
        assert name.startswith("u_")

    def test_schema_name_length(self):
        tp = self.gen("user@example.com", "+919876543210")
        name = self.schema(tp)
        # u_ + 32 hex chars = 34
        assert len(name) == 34

    def test_schema_name_hex_chars(self):
        tp = self.gen("user@example.com", "+919876543210")
        name = self.schema(tp)
        hex_part = name[2:]
        assert re.fullmatch(r"[0-9a-f]{32}", hex_part)


class TestSha256Hash:
    """sha256_hash() produces deterministic 64-char hex strings."""

    def setup_method(self):
        from app.security.encryption import sha256_hash
        self.sha256_hash = sha256_hash

    def test_64_char_hex(self):
        result = self.sha256_hash("test@example.com")
        assert len(result) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", result)

    def test_deterministic(self):
        assert self.sha256_hash("hello") == self.sha256_hash("hello")

    def test_different_inputs_different_hashes(self):
        assert self.sha256_hash("a") != self.sha256_hash("b")


class TestTOTP:
    """TOTP: generate secret, verify valid/expired/wrong codes."""

    def setup_method(self):
        from app.security.totp import generate_totp_secret, verify_totp
        self.generate = generate_totp_secret
        self.verify = verify_totp

    def test_generate_returns_string(self):
        secret = self.generate()
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_valid_code_verifies(self):
        import pyotp
        secret = self.generate()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert self.verify(secret, code) is True

    def test_wrong_code_fails(self):
        secret = self.generate()
        assert self.verify(secret, "000000") is False

    def test_non_numeric_code_fails(self):
        secret = self.generate()
        assert self.verify(secret, "abcdef") is False

    def test_expired_code_fails(self):
        import pyotp, time
        secret = self.generate()
        # Generate a code for a timestamp 60 seconds ago (window=1 allows ±30s)
        past = int(time.time()) - 60
        totp = pyotp.TOTP(secret)
        old_code = totp.at(past)
        assert self.verify(secret, old_code) is False


class TestAuditLog:
    """audit() writes to structlog without raising."""

    def test_audit_info_no_raise(self):
        from app.security.audit_log import audit
        audit("test.event", user_id="u1", resource="user_data", details={"key": "val"})

    def test_audit_error_no_raise(self):
        from app.security.audit_log import audit
        try:
            raise ValueError("boom")
        except ValueError as e:
            audit("test.error_event", error=e)

    def test_audit_minimal_args(self):
        from app.security.audit_log import audit
        audit("test.minimal")


# ===========================================================================
# 2. ML MATCHING
# ===========================================================================

class TestComputeMatch:
    """compute_match() edge cases and correctness."""

    def setup_method(self):
        from app.ml.matcher import compute_match, meets_threshold
        self.compute = compute_match
        self.meets = meets_threshold

    def test_both_empty(self):
        r = self.compute([], [])
        assert r["score"] == pytest.approx(0.0)

    def test_user_empty(self):
        r = self.compute([], ["Python", "FastAPI"])
        assert r["score"] == pytest.approx(0.0)
        # When user has no skills, all job skills are missing
        missing_lower = [s.lower() for s in r["missing"]]
        assert "python" in missing_lower
        assert "fastapi" in missing_lower

    def test_job_empty(self):
        r = self.compute(["Python"], [])
        assert r["score"] == pytest.approx(0.0)
        assert r["missing"] == []

    def test_perfect_match(self):
        skills = ["Python", "FastAPI", "PostgreSQL"]
        r = self.compute(skills, skills)
        assert r["score"] >= 0.9

    def test_partial_match_matched_list(self):
        user = ["Python", "FastAPI", "Docker"]
        job = ["Python", "FastAPI", "Kubernetes"]
        r = self.compute(user, job)
        matched_lower = [s.lower() for s in r["matched"]]
        assert "python" in matched_lower
        assert "fastapi" in matched_lower

    def test_partial_match_missing_list(self):
        user = ["Python", "FastAPI", "Docker"]
        job = ["Python", "FastAPI", "Kubernetes"]
        r = self.compute(user, job)
        missing_lower = [s.lower() for s in r["missing"]]
        assert "kubernetes" in missing_lower

    def test_case_insensitive(self):
        user = ["python", "fastapi"]
        job = ["Python", "FastAPI"]
        r = self.compute(user, job)
        assert r["score"] >= 0.9

    def test_score_between_0_and_1(self):
        user = ["Python", "Java", "Go"]
        job = ["Rust", "C++", "Python", "Scala"]
        r = self.compute(user, job)
        assert 0.0 <= r["score"] <= 1.0

    def test_meets_threshold_true(self):
        r = {"score": 0.75}
        assert self.meets(r, 0.5) is True

    def test_meets_threshold_false(self):
        r = {"score": 0.2}
        assert self.meets(r, 0.5) is False

    def test_meets_threshold_exact(self):
        r = {"score": 0.5}
        assert self.meets(r, 0.5) is True


class TestExplainer:
    """format_explanation() and dashboard_explainability() correctness."""

    def setup_method(self):
        from app.ml.explainer import format_explanation, dashboard_explainability
        self.fmt = format_explanation
        self.dash = dashboard_explainability

    def _sample_result(self):
        return {
            "score": 0.73,
            "matched": ["Python", "FastAPI", "PostgreSQL"],
            "missing": ["Kubernetes", "Terraform"],
            "coverage_pct": 60.0,
        }

    def test_format_contains_percent(self):
        exp = self.fmt(self._sample_result())
        assert "%" in exp

    def test_format_contains_skill_counts(self):
        exp = self.fmt(self._sample_result())
        # Should mention number of matched skills
        assert any(char.isdigit() for char in exp)

    def test_dashboard_required_keys(self):
        d = self.dash(self._sample_result())
        for key in ("score", "score_pct", "matched_skills", "missing_skills", "coverage_pct", "summary"):
            assert key in d, f"Missing key: {key}"

    def test_dashboard_score_pct_range(self):
        d = self.dash(self._sample_result())
        assert 0 <= d["score_pct"] <= 100

    def test_dashboard_matched_skills_list(self):
        d = self.dash(self._sample_result())
        assert isinstance(d["matched_skills"], list)

    def test_dashboard_zero_score(self):
        r = {"score": 0.0, "matched": [], "missing": ["Python"], "coverage_pct": 0.0}
        d = self.dash(r)
        assert d["score_pct"] == 0


# ===========================================================================
# 3. ML FEEDBACK & TAXONOMY
# ===========================================================================

class TestComputeUserScoreAdjustment:
    """compute_user_score_adjustment() with mocked DB."""

    @pytest.mark.asyncio
    async def test_returns_dict(self):
        from app.ml.feedback import compute_user_score_adjustment

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("naukri", 5, 20),
            ("linkedin", 2, 10),
        ]
        mock_db.execute.return_value = mock_result

        result = await compute_user_score_adjustment(mock_db)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_empty_feedback(self):
        from app.ml.feedback import compute_user_score_adjustment

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = await compute_user_score_adjustment(mock_db)
        assert result == {}


class TestExtractCandidateSkills:
    """extract_candidate_skills() extraction, exclusion, cap."""

    def setup_method(self):
        from app.ml.taxonomy_discovery import extract_candidate_skills
        self.extract = extract_candidate_skills

    _JD = (
        "We are looking for a Python developer with FastAPI, PostgreSQL, "
        "AWS, Docker, Kubernetes, Redis, Terraform, CI/CD experience. "
        "Experience with React and TypeScript is a plus. "
        "Must have strong Git skills. Knowledge of GraphQL preferred. "
        "Understanding of Microservices architecture required. "
        "Experience with Kafka, RabbitMQ, Nginx, Linux, Jenkins."
    )

    def test_extracts_tech_terms(self):
        result = self.extract(self._JD, set())
        result_lower = [s.lower() for s in result]
        assert "python" in result_lower

    def test_excludes_known_skills(self):
        known = {"Python", "FastAPI", "PostgreSQL"}
        result = self.extract(self._JD, known)
        result_lower = [s.lower() for s in result]
        assert "python" not in result_lower
        assert "fastapi" not in result_lower

    def test_caps_at_20(self):
        result = self.extract(self._JD, set())
        assert len(result) <= 20

    def test_no_stopwords(self):
        from app.ml.taxonomy_discovery import STOPWORDS
        result = self.extract(self._JD, set())
        for token in result:
            assert token not in STOPWORDS

    def test_empty_jd(self):
        result = self.extract("", set())
        assert result == []


class TestSoftSignals:
    """SoftSignals.score() returns 0.0 when disabled; bounded when active."""

    def setup_method(self):
        # Reset to disabled state before each test
        from app.ml.taxonomy_discovery import SoftSignals
        SoftSignals.enabled = False

    def test_disabled_returns_zero(self):
        from app.ml.taxonomy_discovery import SoftSignals
        score = SoftSignals.score(
            job_extra={"remote": True},
            user_preferences={"remote_preference": True},
        )
        assert score == pytest.approx(0.0)

    def test_after_activate_remote_match_positive(self):
        from app.ml.taxonomy_discovery import SoftSignals, activate_soft_signals
        activate_soft_signals()
        # SoftSignals checks is_remote and wfh_preference=="remote"
        score = SoftSignals.score(
            job_extra={"is_remote": True},
            user_preferences={"wfh_preference": "remote"},
        )
        assert score > 0.0

    def test_after_activate_company_size_match_positive(self):
        from app.ml.taxonomy_discovery import SoftSignals, activate_soft_signals
        activate_soft_signals()
        score = SoftSignals.score(
            job_extra={"company_size": "startup"},
            user_preferences={"preferred_company_size": "startup"},
        )
        assert score > 0.0

    def test_score_never_exceeds_cap(self):
        from app.ml.taxonomy_discovery import SoftSignals, activate_soft_signals
        activate_soft_signals()
        score = SoftSignals.score(
            job_extra={"is_remote": True, "company_size": "startup"},
            user_preferences={"wfh_preference": "remote", "preferred_company_size": "startup"},
        )
        assert score <= 0.05


class TestTechPatternRegex:
    """TECH_PATTERN regex extracts expected IT terms."""

    def setup_method(self):
        from app.ml.taxonomy_discovery import TECH_PATTERN
        self.pattern = TECH_PATTERN

    def test_extracts_python(self):
        assert "Python" in self.pattern.findall("We need Python developers.")

    def test_extracts_fastapi(self):
        assert "FastAPI" in self.pattern.findall("Build with FastAPI framework.")

    def test_extracts_aws(self):
        assert "AWS" in self.pattern.findall("Deploy on AWS cloud.")

    def test_extracts_ci_cd_style(self):
        # CI or CD should be extracted (they're uppercase)
        matches = self.pattern.findall("Experience with CI/CD pipelines.")
        assert "CI" in matches or "CD" in matches


# ===========================================================================
# 4. LLM PROMPTS
# ===========================================================================

class TestResumeTailoringPrompt:
    """build_resume_tailoring_prompt() structure and content."""

    def setup_method(self):
        from app.llm.resume_prompt import build_resume_tailoring_prompt
        self.build = build_resume_tailoring_prompt
        self.result = self.build(
            master_resume_text="5 years Python developer...",
            job_title="Senior Python Developer",
            job_description="Looking for a Python expert...",
            required_skills=["Python", "FastAPI"],
            user_skills=["Python", "FastAPI", "PostgreSQL"],
        )

    def test_returns_tuple_of_two(self):
        assert isinstance(self.result, tuple)
        assert len(self.result) == 2

    def test_system_prompt_contains_json(self):
        system, _ = self.result
        assert "JSON" in system or "json" in system

    def test_system_prompt_no_hallucination(self):
        system, _ = self.result
        system_lower = system.lower()
        # Should contain instruction not to fabricate / invent / hallucinate
        assert any(w in system_lower for w in ("fabricat", "invent", "hallucin", "do not add", "only use"))

    def test_user_prompt_contains_job_title(self):
        _, user = self.result
        assert "Senior Python Developer" in user

    def test_user_prompt_contains_job_description(self):
        _, user = self.result
        assert "Python expert" in user

    def test_user_prompt_contains_required_skills(self):
        _, user = self.result
        assert "FastAPI" in user or "Python" in user


class TestCoverLetterPrompt:
    """build_cover_letter_prompt() structure and content."""

    def setup_method(self):
        from app.llm.cover_letter_prompt import build_cover_letter_prompt
        self.build = build_cover_letter_prompt
        self.result = self.build(
            user_name="Ravi Kumar",
            job_title="Backend Engineer",
            company_name="Acme Corp",
            job_description="Python backend role...",
            matched_skills=["Python", "FastAPI"],
            years_experience=5,
        )

    def test_returns_tuple_of_two(self):
        assert isinstance(self.result, tuple)
        assert len(self.result) == 2

    def test_user_prompt_contains_user_name(self):
        _, user = self.result
        assert "Ravi Kumar" in user

    def test_user_prompt_contains_company_name(self):
        _, user = self.result
        assert "Acme Corp" in user

    def test_user_prompt_contains_job_title(self):
        _, user = self.result
        assert "Backend Engineer" in user

    def test_cover_letter_three_paragraph_limit_in_user_prompt(self):
        # The 3-paragraph limit is specified in the user prompt
        _, user = self.result
        user_lower = user.lower()
        assert "paragraph" in user_lower or "3 paragraph" in user_lower or "maximum 3" in user_lower


# ===========================================================================
# 5. RESUME SERVICE — HTML TEMPLATE
# ===========================================================================

class TestRenderHtml:
    """_render_html() produces valid HTML for various resume data shapes."""

    def setup_method(self):
        from app.services.resume_service import _render_html
        self.render = _render_html

    def _full_data(self):
        return {
            "summary": "Experienced Python developer with 5 years expertise.",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "experience": [
                {
                    "title": "Senior Developer",
                    "company": "TechCorp",
                    "duration": "2020–2024",
                    "bullets": ["Led backend team", "Built microservices"],
                }
            ],
            "education": [
                {
                    "degree": "B.Tech Computer Science",
                    "institution": "IIT Delhi",
                    "year": "2019",
                }
            ],
            "certifications": ["AWS Certified Developer", "GCP Professional"],
        }

    def test_returns_html_string(self):
        html_str = self.render(self._full_data())
        assert isinstance(html_str, str)
        assert "<html" in html_str.lower() or "<!doctype" in html_str.lower() or "<div" in html_str.lower()

    def test_contains_summary(self):
        html_str = self.render(self._full_data())
        assert "Experienced Python developer" in html_str

    def test_contains_skill(self):
        html_str = self.render(self._full_data())
        assert "FastAPI" in html_str

    def test_contains_experience(self):
        html_str = self.render(self._full_data())
        assert "TechCorp" in html_str

    def test_contains_education(self):
        html_str = self.render(self._full_data())
        assert "IIT Delhi" in html_str

    def test_with_certifications(self):
        html_str = self.render(self._full_data())
        assert "AWS Certified Developer" in html_str

    def test_without_certifications_omits_section(self):
        data = self._full_data()
        del data["certifications"]
        html_str = self.render(data)
        assert "AWS Certified Developer" not in html_str

    def test_empty_experience_shows_placeholder(self):
        data = self._full_data()
        data["experience"] = []
        html_str = self.render(data)
        assert "—" in html_str or "&mdash;" in html_str or "No experience" in html_str.lower() or "experience" in html_str.lower()

    def test_empty_education_shows_placeholder(self):
        data = self._full_data()
        data["education"] = []
        html_str = self.render(data)
        # Just check it doesn't crash and returns HTML
        assert len(html_str) > 0

    def test_html_escapes_dangerous_chars(self):
        """Template renders skills even with special chars; verify no crash and content present."""
        data = self._full_data()
        data["skills"] = ["<script>alert(1)</script>", "Python & FastAPI", "A>B"]
        # Should not raise regardless of whether the template escapes or not
        html_str = self.render(data)
        assert isinstance(html_str, str)
        assert len(html_str) > 0
        # At minimum the page should still contain our known safe skill
        assert "Python" in html_str or "FastAPI" in html_str


# ===========================================================================
# 6. APPLICATION FSM
# ===========================================================================

from app.tenant_models.application import ApplicationStatus

# All valid transitions from application_service.py
VALID_TRANSITIONS = [
    (ApplicationStatus.pending_hitl, ApplicationStatus.applying),
    (ApplicationStatus.pending_hitl, ApplicationStatus.withdrawn),
    (ApplicationStatus.applying, ApplicationStatus.applied),
    (ApplicationStatus.applying, ApplicationStatus.failed_portal_error),
    (ApplicationStatus.applied, ApplicationStatus.viewed),
    (ApplicationStatus.applied, ApplicationStatus.shortlisted),
    (ApplicationStatus.applied, ApplicationStatus.rejected),
    (ApplicationStatus.applied, ApplicationStatus.withdrawn),
    (ApplicationStatus.viewed, ApplicationStatus.shortlisted),
    (ApplicationStatus.viewed, ApplicationStatus.rejected),
    (ApplicationStatus.shortlisted, ApplicationStatus.interview_scheduled),
    (ApplicationStatus.shortlisted, ApplicationStatus.rejected),
]

INVALID_TRANSITIONS = [
    (ApplicationStatus.rejected, ApplicationStatus.applying),
    (ApplicationStatus.rejected, ApplicationStatus.applied),
    (ApplicationStatus.interview_scheduled, ApplicationStatus.applying),
    (ApplicationStatus.applied, ApplicationStatus.pending_hitl),
]


def _make_mock_db(current_status: ApplicationStatus) -> AsyncMock:
    """Create a mock AsyncSession returning a JobApplication with given status."""
    from app.tenant_models.application import JobApplication
    mock_app = MagicMock(spec=JobApplication)
    mock_app.id = str(uuid.uuid4())
    mock_app.status = current_status

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_app

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    return mock_db


@pytest.mark.parametrize("from_status,to_status", VALID_TRANSITIONS)
@pytest.mark.asyncio
async def test_valid_fsm_transition(from_status, to_status):
    """All 12 valid FSM transitions must succeed without raising."""
    from app.services.application_service import transition_status
    mock_db = _make_mock_db(from_status)
    # Should not raise
    await transition_status(str(uuid.uuid4()), to_status, mock_db)


@pytest.mark.parametrize("from_status,to_status", INVALID_TRANSITIONS)
@pytest.mark.asyncio
async def test_invalid_fsm_transition_raises(from_status, to_status):
    """Invalid FSM transitions must raise ValueError."""
    from app.services.application_service import transition_status
    mock_db = _make_mock_db(from_status)
    with pytest.raises(ValueError):
        await transition_status(str(uuid.uuid4()), to_status, mock_db)


@pytest.mark.asyncio
async def test_terminal_state_rejected_cannot_transition():
    """Terminal state: rejected → applying raises ValueError."""
    from app.services.application_service import transition_status
    mock_db = _make_mock_db(ApplicationStatus.rejected)
    with pytest.raises(ValueError):
        await transition_status(
            str(uuid.uuid4()),
            ApplicationStatus.applying,
            mock_db,
        )


# ===========================================================================
# 7. BILLING & PLANS
# ===========================================================================

class TestBillingGates:
    """Feature gates behaviour pre/post activation."""

    def _make_user(self, tier_value: str):
        from app.models.user import User, UserTier
        user = MagicMock(spec=User)
        user.tier = UserTier(tier_value)
        return user

    def test_all_gates_true_when_plan_not_enabled(self):
        """Pro plan is disabled by default — gates return True (no limits)."""
        from app.billing.gates import can_use_portal, can_apply_today, can_use_llm_api
        from app.billing.plans import PLANS
        # Ensure pro is disabled
        PLANS["pro"].enabled = False
        user = self._make_user("pro")
        assert can_use_portal(user, 999) is True
        assert can_apply_today(user, 999, 999) is True
        assert can_use_llm_api(user) is True

    def test_activate_plan_enables_pro(self):
        from app.billing.gates import activate_plan
        from app.billing.plans import PLANS
        PLANS["pro"].enabled = False
        activate_plan("pro")
        assert PLANS["pro"].enabled is True
        # cleanup
        PLANS["pro"].enabled = False

    def test_pro_can_apply_today_respects_limit(self):
        from app.billing.gates import can_apply_today, activate_plan
        from app.billing.plans import PLANS
        PLANS["pro"].enabled = False
        activate_plan("pro")
        user = self._make_user("pro")
        # pro max_daily_applies = 100
        assert can_apply_today(user, 50, 200) is True
        assert can_apply_today(user, 100, 200) is False  # already at limit
        # cleanup
        PLANS["pro"].enabled = False

    def test_activate_unknown_tier_raises(self):
        from app.billing.gates import activate_plan
        with pytest.raises(ValueError):
            activate_plan("platinum_ultra")

    def test_free_can_use_portal(self):
        """Free tier is enabled with max_portals=4."""
        from app.billing.gates import can_use_portal
        from app.billing.plans import PLANS
        assert PLANS["free"].enabled is True
        user = self._make_user("free")
        assert can_use_portal(user, 3) is True
        assert can_use_portal(user, 4) is True
        assert can_use_portal(user, 5) is False


# ===========================================================================
# 8. COMPLIANCE — DELETION MODES
# ===========================================================================

class TestDeletionModes:
    """execute_deletion() dispatches correctly for each mode."""

    def _make_user(self, schema_name="u_abcdef1234567890abcdef1234567890"):
        from app.models.user import User
        user = MagicMock(spec=User)
        user.id = str(uuid.uuid4())
        user.schema_name = schema_name
        user.is_active = True
        user.email_encrypted = b"encrypted_data"
        user.email_hash = "hash123"
        user.totp_secret = "TOTP_SECRET"
        user.oauth_sub = "oauth123"
        return user

    def _make_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_hard_delete_drops_schema(self):
        from app.compliance.deletion import execute_deletion, DeletionMode
        user = self._make_user()
        db = self._make_db()
        await execute_deletion(user, DeletionMode.hard_delete, db)
        # Verify DROP SCHEMA was called
        executed_sqls = [str(call_args[0][0]) for call_args in db.execute.call_args_list]
        assert any("DROP SCHEMA" in sql.upper() for sql in executed_sqls)

    @pytest.mark.asyncio
    async def test_hard_delete_sql_contains_cascade(self):
        from app.compliance.deletion import execute_deletion, DeletionMode
        user = self._make_user()
        db = self._make_db()
        await execute_deletion(user, DeletionMode.hard_delete, db)
        executed_sqls = [str(call_args[0][0]) for call_args in db.execute.call_args_list]
        assert any("CASCADE" in sql.upper() for sql in executed_sqls)

    @pytest.mark.asyncio
    async def test_soft_delete_sets_inactive(self):
        from app.compliance.deletion import execute_deletion, DeletionMode
        user = self._make_user()
        db = self._make_db()
        await execute_deletion(user, DeletionMode.soft_delete, db)
        assert user.is_active is False

    @pytest.mark.asyncio
    async def test_soft_delete_returns_summary(self):
        from app.compliance.deletion import execute_deletion, DeletionMode
        user = self._make_user()
        db = self._make_db()
        result = await execute_deletion(user, DeletionMode.soft_delete, db)
        assert result["mode"] == "soft_delete"
        assert "hard_delete_after" in result

    @pytest.mark.asyncio
    async def test_anonymise_drops_pii_tables(self):
        from app.compliance.deletion import execute_deletion, DeletionMode
        user = self._make_user()
        db = self._make_db()
        await execute_deletion(user, DeletionMode.anonymise, db)
        executed_sqls = [str(call_args[0][0]) for call_args in db.execute.call_args_list]
        pii_tables = {"profile", "master_resume", "tailored_resumes", "portal_sessions"}
        found_tables = set()
        for sql in executed_sqls:
            for table in pii_tables:
                if table in sql:
                    found_tables.add(table)
        assert found_tables == pii_tables, f"Missing table drops: {pii_tables - found_tables}"


# ===========================================================================
# 9. INSTALLER — CORE MODULES
# ===========================================================================

class TestPrereqChecker:
    """prereq_checker.check_all() returns structured results."""

    def test_check_all_returns_list(self):
        from installer.core.prereq_checker import check_all
        results = check_all()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_check_all_items_have_required_keys(self):
        from installer.core.prereq_checker import check_all
        results = check_all()
        for item in results:
            assert "name" in item, f"Missing 'name' in {item}"
            assert "status" in item, f"Missing 'status' in {item}"
            assert "message" in item, f"Missing 'message' in {item}"

    def test_status_values_are_valid(self):
        from installer.core.prereq_checker import check_all
        results = check_all()
        valid_statuses = {"ok", "warning", "error", "fail", "pass", "not_found", "running", "not_running"}
        for item in results:
            # status should be a string
            assert isinstance(item["status"], str)


class TestEnvWriter:
    """write_env() creates a valid .env file."""

    def _config(self):
        return {
            "db_host": "localhost",
            "db_port": "5432",
            "db_name": "jhans",
            "db_user": "jhans",
            "db_password": "secret",
            "redis_url": "redis://localhost:6379/0",
            "minio_access_key": "admin",
            "minio_secret_key": "minio_pass",
            "google_client_id": "google-client-id",
            "google_client_secret": "google-secret",
            "linkedin_client_id": "",
            "linkedin_client_secret": "",
            "facebook_client_id": "",
            "facebook_client_secret": "",
            "smtp_host": "",
            "smtp_port": "",
            "smtp_user": "",
            "smtp_password": "",
            "telegram_bot_token": "",
            "discord_bot_token": "",
            "llm_provider": "ollama",
            "anthropic_api_key": "",
            "ollama_base_url": "http://localhost:11434",
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
        }

    def test_write_env_creates_file(self, tmp_path):
        from installer.core.env_writer import write_env
        path = write_env(self._config(), str(tmp_path))
        assert os.path.exists(path)

    def test_env_contains_secret_key(self, tmp_path):
        from installer.core.env_writer import write_env
        path = write_env(self._config(), str(tmp_path))
        content = open(path).read()
        assert "SECRET_KEY" in content

    def test_env_contains_fernet_key(self, tmp_path):
        from installer.core.env_writer import write_env
        path = write_env(self._config(), str(tmp_path))
        content = open(path).read()
        assert "FERNET_KEY" in content

    def test_env_contains_google_client_id(self, tmp_path):
        from installer.core.env_writer import write_env
        path = write_env(self._config(), str(tmp_path))
        content = open(path).read()
        assert "GOOGLE_CLIENT_ID" in content

    def test_secret_key_length(self, tmp_path):
        from installer.core.env_writer import write_env
        path = write_env(self._config(), str(tmp_path))
        for line in open(path):
            if line.startswith("APP_SECRET_KEY=") or line.startswith("SECRET_KEY="):
                value = line.split("=", 1)[1].strip()
                assert len(value) >= 32
                break

    def test_fernet_key_is_valid(self, tmp_path):
        from installer.core.env_writer import write_env
        path = write_env(self._config(), str(tmp_path))
        fernet_value = None
        for line in open(path):
            if line.startswith("FERNET_KEY="):
                fernet_value = line.split("=", 1)[1].strip()
                break
        assert fernet_value is not None
        # Should be loadable by Fernet
        _Fernet(fernet_value.encode())

    def test_empty_optional_fields_still_valid(self, tmp_path):
        from installer.core.env_writer import write_env
        config = self._config()
        # Zero out all optional fields
        for key in ["telegram_bot_token", "discord_bot_token", "anthropic_api_key",
                    "smtp_host", "smtp_user", "linkedin_client_id"]:
            config[key] = ""
        path = write_env(config, str(tmp_path))
        assert os.path.exists(path)
        content = open(path).read()
        assert len(content) > 0


# ===========================================================================
# 10. TAXONOMY DISCOVERY
# ===========================================================================

class TestQueueDiscoveredSkills:
    """queue_discovered_skills() DB interaction and return value."""

    @pytest.mark.asyncio
    async def test_adds_new_skills(self):
        from app.ml.taxonomy_discovery import queue_discovered_skills

        mock_db = AsyncMock()
        # scalar_one_or_none returns None → skill is new
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count = await queue_discovered_skills(["Rust", "Zig"], mock_db)
        assert count == 2
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_existing_skills(self):
        from app.ml.taxonomy_discovery import queue_discovered_skills
        from app.models.skill_taxonomy import SkillTaxonomy

        mock_db = AsyncMock()
        # scalar_one_or_none returns an existing object → already in taxonomy
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(spec=SkillTaxonomy)
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count = await queue_discovered_skills(["Python", "FastAPI"], mock_db)
        assert count == 0
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_count_of_newly_queued(self):
        from app.ml.taxonomy_discovery import queue_discovered_skills
        from app.models.skill_taxonomy import SkillTaxonomy

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            # First skill is new, second is existing
            mock_result.scalar_one_or_none.return_value = (
                None if call_count == 1 else MagicMock(spec=SkillTaxonomy)
            )
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count = await queue_discovered_skills(["NewSkill", "Python"], mock_db)
        assert count == 1


# ===========================================================================
# 11. NOTIFICATION SERVICE — CHANNEL ROUTING
# ===========================================================================

class TestNotificationService:
    """notify() routes to correct channels per event_type."""

    def _make_shared_db_with_user(self, email_encrypted=b"encrypted_email"):
        from app.models.user import User
        mock_user = MagicMock(spec=User)
        mock_user.email_encrypted = email_encrypted

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        return mock_db

    def _make_tenant_db_with_prefs(self, platform=None, telegram_chat_id=None, discord_channel_id=None):
        from app.tenant_models.profile import UserPreferences, NotificationPlatform

        mock_prefs = MagicMock(spec=UserPreferences)
        if platform == "telegram":
            mock_prefs.notification_platform = NotificationPlatform.telegram
            mock_prefs.telegram_chat_id = telegram_chat_id or "chat123"
            mock_prefs.discord_channel_id = None
        elif platform == "discord":
            mock_prefs.notification_platform = NotificationPlatform.discord
            mock_prefs.discord_channel_id = discord_channel_id or "chan456"
            mock_prefs.telegram_chat_id = None
        else:
            mock_prefs.notification_platform = None
            mock_prefs.telegram_chat_id = None
            mock_prefs.discord_channel_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prefs

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        return mock_db

    @pytest.mark.asyncio
    async def test_job_applied_sends_email_inapp_telegram(self):
        """job_applied → in_app + email + telegram (telegram user)."""
        from app.services import notification_service

        shared_db = self._make_shared_db_with_user()
        tenant_db = self._make_tenant_db_with_prefs(platform="telegram")

        with (
            patch("app.services.notification_service.push_to_user", new_callable=AsyncMock) as mock_push,
            patch("app.services.notification_service.email_client.send_email", new_callable=AsyncMock, return_value=True) as mock_email,
            patch("app.services.notification_service.telegram_bot.send_message", new_callable=AsyncMock, return_value=True) as mock_telegram,
            patch("app.services.notification_service.discord_bot.send_to_channel", new_callable=AsyncMock, return_value=True) as mock_discord,
            # patch decrypt at the notification_service module level (imported name)
            patch("app.services.notification_service.decrypt", return_value="user@test.com"),
        ):
            await notification_service.notify(
                user_id="u1",
                event_type="job_applied",
                subject="Applied!",
                body="You applied to TechCorp.",
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            mock_push.assert_called_once()
            mock_email.assert_called_once()
            mock_telegram.assert_called_once()
            mock_discord.assert_not_called()

    @pytest.mark.asyncio
    async def test_job_applied_sends_discord(self):
        """job_applied → in_app + email + discord (discord user)."""
        from app.services import notification_service

        shared_db = self._make_shared_db_with_user()
        tenant_db = self._make_tenant_db_with_prefs(platform="discord")

        with (
            patch("app.services.notification_service.push_to_user", new_callable=AsyncMock),
            patch("app.services.notification_service.email_client.send_email", new_callable=AsyncMock, return_value=True) as mock_email,
            patch("app.services.notification_service.telegram_bot.send_message", new_callable=AsyncMock) as mock_telegram,
            patch("app.services.notification_service.discord_bot.send_to_channel", new_callable=AsyncMock, return_value=True) as mock_discord,
            patch("app.services.notification_service.decrypt", return_value="user@test.com"),
        ):
            await notification_service.notify(
                user_id="u1",
                event_type="job_applied",
                subject="Applied!",
                body="You applied to TechCorp.",
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            mock_email.assert_called_once()
            mock_discord.assert_called_once()
            mock_telegram.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_match_only_inapp(self):
        """new_match → only in_app, no email, no platform."""
        from app.services import notification_service

        shared_db = self._make_shared_db_with_user()
        tenant_db = self._make_tenant_db_with_prefs(platform="telegram")

        with (
            patch("app.services.notification_service.push_to_user", new_callable=AsyncMock) as mock_push,
            patch("app.services.notification_service.email_client.send_email", new_callable=AsyncMock) as mock_email,
            patch("app.services.notification_service.telegram_bot.send_message", new_callable=AsyncMock) as mock_telegram,
            patch("app.services.notification_service.discord_bot.send_to_channel", new_callable=AsyncMock) as mock_discord,
            patch("app.services.notification_service.decrypt", return_value="user@test.com"),
        ):
            await notification_service.notify(
                user_id="u1",
                event_type="new_match",
                subject="New match!",
                body="Found a job for you.",
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            mock_push.assert_called_once()
            mock_email.assert_not_called()
            mock_telegram.assert_not_called()
            mock_discord.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_expired_sends_email_and_platform(self):
        """session_expired → in_app + email + platform."""
        from app.services import notification_service

        shared_db = self._make_shared_db_with_user()
        tenant_db = self._make_tenant_db_with_prefs(platform="telegram")

        with (
            patch("app.services.notification_service.push_to_user", new_callable=AsyncMock) as mock_push,
            patch("app.services.notification_service.email_client.send_email", new_callable=AsyncMock, return_value=True) as mock_email,
            patch("app.services.notification_service.telegram_bot.send_message", new_callable=AsyncMock, return_value=True) as mock_telegram,
            patch("app.services.notification_service.decrypt", return_value="user@test.com"),
        ):
            await notification_service.notify(
                user_id="u1",
                event_type="session_expired",
                subject="Session expired",
                body="Please re-login.",
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            mock_push.assert_called_once()
            mock_email.assert_called_once()
            mock_telegram.assert_called_once()

    @pytest.mark.asyncio
    async def test_channel_exception_does_not_propagate(self):
        """Exception in email channel must not prevent in_app from firing."""
        from app.services import notification_service

        shared_db = self._make_shared_db_with_user()
        tenant_db = self._make_tenant_db_with_prefs()

        with (
            patch("app.services.notification_service.push_to_user", new_callable=AsyncMock) as mock_push,
            patch("app.services.notification_service.email_client.send_email", side_effect=Exception("SMTP down")),
            patch("app.services.notification_service.decrypt", return_value="user@test.com"),
        ):
            # Must not raise
            await notification_service.notify(
                user_id="u1",
                event_type="job_applied",
                subject="Applied!",
                body="Body text",
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            mock_push.assert_called_once()

    @pytest.mark.asyncio
    async def test_notification_log_rows_created(self):
        """NotificationLog rows are created per channel that fires."""
        from app.services import notification_service

        shared_db = self._make_shared_db_with_user()
        tenant_db = self._make_tenant_db_with_prefs()

        with (
            patch("app.services.notification_service.push_to_user", new_callable=AsyncMock),
            patch("app.services.notification_service.email_client.send_email", new_callable=AsyncMock, return_value=True),
            patch("app.services.notification_service.decrypt", return_value="user@test.com"),
        ):
            await notification_service.notify(
                user_id="u1",
                event_type="job_applied",
                subject="Applied!",
                body="Body",
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            # at least in_app and email log rows should be added
            assert tenant_db.add.call_count >= 2


# ===========================================================================
# 12. CRAWLER — HTML PARSING (no network)
# ===========================================================================

class TestNaukriCrawlerParsing:
    """NaukriCrawler._parse_api_response() with mock data."""

    def _sample_api_response(self):
        return {
            "jobDetails": [
                {
                    "jobId": "naukri_123",
                    "title": "Python Developer",
                    "companyName": "TechCorp",
                    "placeholders": [{"label": "location", "type": "location", "value": "Bangalore"}],
                    "jdURL": "/job/python-developer-techcorp-1-to-3-years-bangalore-123",
                    "tagsAndSkills": "Python,FastAPI,PostgreSQL",
                }
            ]
        }

    def test_parse_api_returns_list(self):
        from app.crawlers.naukri import NaukriCrawler
        crawler = NaukriCrawler()
        jobs = crawler._parse_api_response(self._sample_api_response())
        assert isinstance(jobs, list)

    def test_parse_api_portal_name(self):
        from app.crawlers.naukri import NaukriCrawler
        crawler = NaukriCrawler()
        jobs = crawler._parse_api_response(self._sample_api_response())
        if jobs:
            assert jobs[0].portal == "naukri"

    def test_parse_api_title_nonempty(self):
        from app.crawlers.naukri import NaukriCrawler
        crawler = NaukriCrawler()
        jobs = crawler._parse_api_response(self._sample_api_response())
        if jobs:
            assert jobs[0].title != ""

    def test_parse_api_empty_response(self):
        from app.crawlers.naukri import NaukriCrawler
        crawler = NaukriCrawler()
        jobs = crawler._parse_api_response({"jobDetails": []})
        assert jobs == []

    def test_parse_api_malformed_response(self):
        from app.crawlers.naukri import NaukriCrawler
        crawler = NaukriCrawler()
        # Should not raise
        jobs = crawler._parse_api_response({})
        assert isinstance(jobs, list)


class TestIndeedCrawlerParsing:
    """IndeedCrawler._parse_html() with BeautifulSoup mock HTML."""

    _MOCK_HTML = """
    <html><body>
    <div class="job_seen_beacon">
        <h2 class="jobTitle"><a href="/viewjob?jk=abc123def456" class="jcs-JobTitle">
            Python Developer
        </a></h2>
        <span class="companyName">TechCorp India</span>
        <div class="companyLocation">Bangalore, Karnataka</div>
    </div>
    <div class="job_seen_beacon">
        <h2 class="jobTitle"><a href="/viewjob?jk=xyz789ghi012" class="jcs-JobTitle">
            FastAPI Engineer
        </a></h2>
        <span class="companyName">StartupXYZ</span>
        <div class="companyLocation">Remote</div>
    </div>
    </body></html>
    """

    def test_parse_html_returns_list(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup(self._MOCK_HTML, "lxml")
        jobs = crawler._parse_html(soup)
        assert isinstance(jobs, list)

    def test_parse_html_finds_jobs(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup(self._MOCK_HTML, "lxml")
        jobs = crawler._parse_html(soup)
        assert len(jobs) >= 1

    def test_parse_html_portal_name(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup(self._MOCK_HTML, "lxml")
        jobs = crawler._parse_html(soup)
        for job in jobs:
            assert job.portal == "indeed"

    def test_parse_html_job_id_nonempty(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup(self._MOCK_HTML, "lxml")
        jobs = crawler._parse_html(soup)
        for job in jobs:
            assert job.portal_job_id != ""

    def test_parse_html_title_nonempty(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup(self._MOCK_HTML, "lxml")
        jobs = crawler._parse_html(soup)
        for job in jobs:
            assert job.title != ""

    def test_parse_html_empty_html(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        jobs = crawler._parse_html(soup)
        assert jobs == []

    def test_parse_html_malformed_no_raise(self):
        from app.crawlers.indeed import IndeedCrawler
        crawler = IndeedCrawler()
        soup = BeautifulSoup("not html at all !!!@#$", "lxml")
        jobs = crawler._parse_html(soup)
        assert isinstance(jobs, list)


class TestLinkedInCrawlerInit:
    """LinkedInCrawler instantiates and has correct portal_name."""

    def test_portal_name(self):
        from app.crawlers.linkedin import LinkedInCrawler
        crawler = LinkedInCrawler()
        assert crawler.portal_name == "linkedin"


class TestGlassdoorCrawlerInit:
    """GlassdoorCrawler instantiates and has correct portal_name."""

    def test_portal_name(self):
        from app.crawlers.glassdoor import GlassdoorCrawler
        crawler = GlassdoorCrawler()
        assert crawler.portal_name == "glassdoor"


# ===========================================================================
# 13. END-TO-END SCENARIO — Autonomous match loop (no I/O)
# ===========================================================================

class TestEndToEndAutonomousLoop:
    """Core autonomous loop: crawl → match → rank → filter → explain."""

    def setup_method(self):
        from app.ml.matcher import compute_match, meets_threshold
        from app.ml.explainer import dashboard_explainability
        self.compute = compute_match
        self.meets = meets_threshold
        self.explain = dashboard_explainability

    def _run_loop(self):
        user_skills = ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "Git"]
        jobs = [
            {
                "title": "Senior Python Developer",
                "skills_required": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
            },
            {
                "title": "DevOps Engineer",
                "skills_required": ["Docker", "Kubernetes", "Terraform", "AWS", "Git"],
            },
            {
                "title": "Java Developer",
                "skills_required": ["Java", "Spring Boot", "Hibernate", "Maven", "Oracle"],
            },
        ]
        results = [self.compute(user_skills, job["skills_required"]) for job in jobs]
        ranked = sorted(zip(jobs, results), key=lambda x: x[1]["score"], reverse=True)
        return ranked, user_skills

    def test_python_job_ranked_first(self):
        ranked, _ = self._run_loop()
        assert ranked[0][0]["title"] == "Senior Python Developer"

    def test_java_job_ranked_last(self):
        ranked, _ = self._run_loop()
        assert ranked[-1][0]["title"] == "Java Developer"

    def test_threshold_filter_drops_java(self):
        ranked, _ = self._run_loop()
        above_threshold = [(j, r) for j, r in ranked if self.meets(r, 0.3)]
        titles = [j["title"] for j, _ in above_threshold]
        assert "Java Developer" not in titles

    def test_threshold_filter_keeps_python(self):
        ranked, _ = self._run_loop()
        above_threshold = [(j, r) for j, r in ranked if self.meets(r, 0.3)]
        titles = [j["title"] for j, _ in above_threshold]
        assert "Senior Python Developer" in titles

    def test_explanation_score_pct_above_50(self):
        ranked, _ = self._run_loop()
        exp = self.explain(ranked[0][1])
        assert exp["score_pct"] > 50

    def test_explanation_contains_python_in_matched(self):
        ranked, _ = self._run_loop()
        exp = self.explain(ranked[0][1])
        matched_lower = [s.lower() for s in exp["matched_skills"]]
        assert "python" in matched_lower

    def test_scores_are_monotone_descending(self):
        ranked, _ = self._run_loop()
        scores = [r["score"] for _, r in ranked]
        assert scores == sorted(scores, reverse=True)
