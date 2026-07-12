import pytest
from app.ml.taxonomy_discovery import SoftSignals, activate_soft_signals


@pytest.fixture(autouse=True)
def reset_soft_signals():
    original = SoftSignals.enabled
    yield
    SoftSignals.enabled = original


def test_score_returns_zero_when_disabled():
    SoftSignals.enabled = False
    result = SoftSignals.score(
        {"is_remote": True, "company_size": "startup"},
        {"wfh_preference": "remote", "preferred_company_size": "startup"},
    )
    assert result == 0.0


def test_remote_job_with_remote_preference_scores_positive_when_enabled():
    SoftSignals.enabled = True
    result = SoftSignals.score(
        {"is_remote": True},
        {"wfh_preference": "remote"},
    )
    assert result > 0.0


def test_full_remote_preference_also_matches():
    SoftSignals.enabled = True
    result = SoftSignals.score(
        {"is_remote": True},
        {"wfh_preference": "full_remote"},
    )
    assert result > 0.0


def test_company_size_match_adds_score_when_enabled():
    SoftSignals.enabled = True
    result = SoftSignals.score(
        {"company_size": "mid"},
        {"preferred_company_size": "mid"},
    )
    assert result > 0.0


def test_score_never_exceeds_0_05():
    SoftSignals.enabled = True
    result = SoftSignals.score(
        {"is_remote": True, "company_size": "startup"},
        {"wfh_preference": "remote", "preferred_company_size": "startup"},
    )
    assert result <= 0.05


def test_score_is_zero_when_no_match():
    SoftSignals.enabled = True
    result = SoftSignals.score(
        {"is_remote": False, "company_size": "large"},
        {"wfh_preference": "remote", "preferred_company_size": "startup"},
    )
    assert result == 0.0


def test_activate_soft_signals_sets_enabled():
    SoftSignals.enabled = False
    activate_soft_signals()
    assert SoftSignals.enabled is True
