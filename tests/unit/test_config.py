"""
R9: the deployment posture is secure by default.
Given APP_ENV is unset, when settings load, then the app runs as production
(no OpenAPI docs, https-only session cookies). Development is an explicit opt-in,
and an unrecognised APP_ENV fails fast instead of silently meaning "not production".
"""
import pytest
from pydantic import ValidationError

from app.config import Settings


def test_unset_app_env_defaults_to_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    s = Settings(_env_file=None)
    assert s.app_env == "production"
    assert s.is_production is True


def test_development_is_an_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert Settings(_env_file=None).is_production is False


@pytest.mark.parametrize("value", ["prod", "Production", "dev", ""])
def test_unrecognised_app_env_is_rejected(monkeypatch, value):
    monkeypatch.setenv("APP_ENV", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_session_lifetime_defaults_to_four_hours(monkeypatch):
    """Authenticated sessions last 4h by default (product decision 2026-09-25)."""
    monkeypatch.delenv("JWT_EXPIRY_HOURS", raising=False)
    assert Settings(_env_file=None).jwt_expiry_hours == 4
