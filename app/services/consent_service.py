"""
DPDPA consent withdrawal (CHG-007): record it, then stop the processing it covered.

The consent record is the source of truth that the processing paths check; the
side effects here (preference off, account deletion scheduled) follow from it.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import consent_store
from app.compliance.consent_store import Withdrawal
from app.compliance.deletion import DeletionMode, execute_deletion
from app.database import get_tenant_db
from app.models.user import User
from app.tenant_models.profile import UserPreferences


@dataclass(frozen=True)
class WithdrawalOutcome:
    withdrawal: Withdrawal
    account_deletion: dict[str, Any] | None  # soft-delete summary when data_processing went


async def disable_auto_apply(schema_name: str) -> None:
    async for tenant_db in get_tenant_db(schema_name):
        prefs = (await tenant_db.execute(select(UserPreferences))).scalar_one_or_none()
        if prefs is not None and prefs.auto_apply_enabled:
            prefs.auto_apply_enabled = False
            await tenant_db.commit()


async def withdraw(
    user: User, scopes: Iterable[str], ip_address: str, user_agent: str, db: AsyncSession,
) -> WithdrawalOutcome:
    withdrawal = await consent_store.withdraw_consent(user.id, scopes, ip_address, user_agent, db)
    if "auto_apply" in withdrawal.withdrawn:
        await disable_auto_apply(user.schema_name)
    deletion = None
    if "data_processing" in withdrawal.withdrawn:
        # Existing entry point: deactivates the account and schedules hard delete.
        deletion = await execute_deletion(user, DeletionMode.soft_delete, db)
    return WithdrawalOutcome(withdrawal=withdrawal, account_deletion=deletion)
