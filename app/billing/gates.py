"""
Feature gate checks — always returns True (no limits) until billing is activated.
Replace the body of each check when tiers go live.
"""
from app.models.user import User, UserTier
from app.billing.plans import PLANS


def can_use_portal(user: User, portal_count: int) -> bool:
    plan = PLANS.get(user.tier.value, PLANS["free"])
    if not plan.enabled:
        return True
    return plan.max_portals == -1 or portal_count <= plan.max_portals


def can_apply_today(user: User, applied_today: int, cap: int) -> bool:
    plan = PLANS.get(user.tier.value, PLANS["free"])
    if not plan.enabled:
        return True
    effective_cap = min(cap, plan.max_daily_applies) if plan.max_daily_applies != -1 else cap
    return applied_today < effective_cap


def can_use_llm_api(user: User) -> bool:
    plan = PLANS.get(user.tier.value, PLANS["free"])
    if not plan.enabled:
        return True
    return plan.llm_api_access


def activate_plan(tier: str) -> None:
    """
    Called by Super Admin to enable a billing tier.
    Once activated, feature gates start enforcing limits.
    """
    from app.billing.plans import PLANS
    if tier not in PLANS:
        raise ValueError(f"Unknown tier: {tier}")
    PLANS[tier].enabled = True
