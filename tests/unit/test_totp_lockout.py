"""
CHG-006: the per-account TOTP lockout and replay rules, on their own.

Given a user row's counters, when a TOTP attempt fails or succeeds, then the
count, the lock deadline and the last accepted time step change as the story
says. The endpoint wiring is covered in tests/unit/test_auth.py.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import Settings, settings
from app.services import totp_lockout

NOW = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)


def _user(attempts=0, locked_until=None, last_step=None):
    return SimpleNamespace(totp_failed_attempts=attempts, totp_locked_until=locked_until,
                           totp_last_used_step=last_step)


def test_settings_default_to_five_failures_and_fifteen_minutes():
    assert Settings.model_fields["totp_max_failures"].default == 5
    assert Settings.model_fields["totp_lockout_minutes"].default == 15


@pytest.mark.parametrize("locked_until,expected", [
    (None, 0),
    (NOW - timedelta(seconds=1), 0),
    (NOW, 0),
    (NOW + timedelta(seconds=90), 90),
    (NOW + timedelta(seconds=0.2), 1),
], ids=["never", "expired", "expires-now", "90s-left", "rounds-up"])
def test_lock_seconds_left(locked_until, expected):
    assert totp_lockout.lock_seconds_left(_user(locked_until=locked_until), NOW) == expected


@pytest.mark.parametrize("last_step,step,replayed", [
    (None, 100, False), (99, 100, False), (100, 100, True), (101, 100, True),
])
def test_a_step_at_or_before_the_last_accepted_one_is_a_replay(last_step, step, replayed):
    assert totp_lockout.is_replayed_step(_user(last_step=last_step), step) is replayed


def test_failures_below_the_limit_only_count():
    user = _user(attempts=settings.totp_max_failures - 2)
    totp_lockout.record_failure(user, NOW)

    assert user.totp_failed_attempts == settings.totp_max_failures - 1
    assert user.totp_locked_until is None


def test_the_failure_that_reaches_the_limit_locks_and_restarts_the_count():
    user = _user(attempts=settings.totp_max_failures - 1)
    totp_lockout.record_failure(user, NOW)

    assert user.totp_locked_until == NOW + timedelta(minutes=settings.totp_lockout_minutes)
    assert user.totp_failed_attempts == 0


def test_limits_come_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "totp_max_failures", 2)
    monkeypatch.setattr(settings, "totp_lockout_minutes", 1)
    user = _user(attempts=1)
    totp_lockout.record_failure(user, NOW)

    assert user.totp_locked_until == NOW + timedelta(minutes=1)


def test_success_clears_the_count_and_the_lock_and_remembers_the_step():
    user = _user(attempts=3, locked_until=NOW - timedelta(minutes=1), last_step=7)
    totp_lockout.record_success(user, 12)

    assert (user.totp_failed_attempts, user.totp_locked_until, user.totp_last_used_step) == (
        0, None, 12)
