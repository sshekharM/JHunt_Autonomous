"""DPDPA consent: view and withdraw (CHG-007, DPDP Act 2023 s.6(4))."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import consent_store
from app.compliance.consent_store import CONSENT_SCOPES, NoConsentOnRecord
from app.compliance.dpdpa import ConsentRecord
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.consent import (
    ConsentEntry,
    ConsentFlags,
    ConsentView,
    WithdrawConsentRequest,
    WithdrawConsentResponse,
)
from app.services import consent_service

router = APIRouter(prefix="/api/consent", tags=["consent"])

# Column sizes of consent_records.ip_address / user_agent
IP_MAX, USER_AGENT_MAX = 45, 512

CurrentUser = Annotated[User, Depends(get_current_user)]
SharedDB = Annotated[AsyncSession, Depends(get_db)]


def _flags(record: ConsentRecord) -> ConsentFlags:
    return ConsentFlags(**{scope: getattr(record, col) for scope, col in CONSENT_SCOPES.items()})


@router.get("", response_model=ConsentView)
async def get_consent(
    user: CurrentUser,
    db: SharedDB,
) -> ConsentView:
    history = await consent_store.consent_history(user.id, db)
    current = await consent_store.current_consent(user.id, db)
    return ConsentView(
        current=_flags(current) if current else None,
        history=[ConsentEntry(event=r.event, flags=_flags(r), at=r.consented_at) for r in history],
    )


@router.post("/withdraw", response_model=WithdrawConsentResponse)
async def withdraw_consent(
    body: WithdrawConsentRequest,
    request: Request,
    user: CurrentUser,
    db: SharedDB,
) -> WithdrawConsentResponse:
    try:
        outcome = await consent_service.withdraw(
            user, body.scopes,
            (request.client.host if request.client else "unknown")[:IP_MAX],
            request.headers.get("user-agent", "")[:USER_AGENT_MAX],
            db,
        )
    except NoConsentOnRecord:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="No consent on record to withdraw.") from None
    return WithdrawConsentResponse(
        withdrawn=list(outcome.withdrawal.withdrawn),
        current=_flags(outcome.withdrawal.record),
        account_deletion=outcome.account_deletion,
    )
