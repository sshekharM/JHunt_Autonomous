"""
Billing tier definitions — SCAFFOLDED, all tiers inactive at launch.
Developers enable tiers by flipping `enabled = True` per tier.
"""
from dataclasses import dataclass


@dataclass
class Plan:
    name: str
    enabled: bool
    max_portals: int
    max_daily_applies: int
    llm_api_access: bool
    custom_match_threshold: bool
    priority_support: bool


PLANS = {
    "free": Plan(
        name="free",
        enabled=True,
        max_portals=4,
        max_daily_applies=20,
        llm_api_access=True,
        custom_match_threshold=True,
        priority_support=False,
    ),
    "pro": Plan(
        name="pro",
        enabled=False,  # activate when ready
        max_portals=10,
        max_daily_applies=100,
        llm_api_access=True,
        custom_match_threshold=True,
        priority_support=True,
    ),
    "enterprise": Plan(
        name="enterprise",
        enabled=False,  # activate when ready
        max_portals=-1,  # unlimited
        max_daily_applies=-1,
        llm_api_access=True,
        custom_match_threshold=True,
        priority_support=True,
    ),
}
