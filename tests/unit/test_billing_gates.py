import pytest
from unittest.mock import MagicMock
from app.billing.plans import PLANS, Plan
from app.billing.gates import can_use_portal, can_apply_today, can_use_llm_api, activate_plan
from app.models.user import UserTier


@pytest.fixture(autouse=True)
def reset_plan_states():
    original_states = {k: v.enabled for k, v in PLANS.items()}
    yield
    for k, v in PLANS.items():
        v.enabled = original_states[k]


def _user(tier: str):
    u = MagicMock()
    u.tier = UserTier(tier)
    return u


def test_all_gates_return_true_when_plan_disabled():
    PLANS["pro"].enabled = False
    user = _user("pro")
    assert can_use_portal(user, 999) is True
    assert can_apply_today(user, 999, 999) is True
    assert can_use_llm_api(user) is True


def test_activate_plan_sets_enabled():
    PLANS["pro"].enabled = False
    activate_plan("pro")
    assert PLANS["pro"].enabled is True


def test_activate_unknown_plan_raises():
    with pytest.raises(ValueError, match="Unknown tier"):
        activate_plan("platinum_ultra")


def test_portal_gate_enforces_limit_after_activation():
    activate_plan("pro")
    user = _user("pro")
    assert can_use_portal(user, PLANS["pro"].max_portals) is True
    assert can_use_portal(user, PLANS["pro"].max_portals + 1) is False


def test_apply_gate_enforces_limit_after_activation():
    activate_plan("pro")
    user = _user("pro")
    assert can_apply_today(user, 0, PLANS["pro"].max_daily_applies) is True
    assert can_apply_today(user, PLANS["pro"].max_daily_applies, PLANS["pro"].max_daily_applies) is False


def test_llm_gate_respects_plan_after_activation():
    activate_plan("pro")
    user = _user("pro")
    assert can_use_llm_api(user) is PLANS["pro"].llm_api_access


def test_enterprise_unlimited_portals_after_activation():
    activate_plan("enterprise")
    user = _user("enterprise")
    assert can_use_portal(user, 10000) is True


def test_activate_free_tier_already_enabled():
    # free tier is already enabled at startup — activating it again is idempotent
    activate_plan("free")
    assert PLANS["free"].enabled is True
