from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.dpdpa import ConsentRecord
from app.models.user import User
from app.security.audit_log import audit

CURRENT_CONSENT_VERSION = "1.0"

# Scope a user can withdraw -> the ConsentRecord flag that records it (CHG-007)
CONSENT_SCOPES: dict[str, str] = {
    "auto_apply": "consented_to_auto_apply",
    "llm_processing": "consented_to_llm_processing",
    "data_processing": "consented_to_data_processing",
}


class NoConsentOnRecord(LookupError):
    """The user has no consent record, so there is nothing to withdraw."""


@dataclass(frozen=True)
class Withdrawal:
    record: ConsentRecord  # the user's consent after the call
    withdrawn: tuple[str, ...]  # scopes this call withdrew; empty when nothing changed

CONSENT_TEXT = """
By completing sign-up you agree that jH_ANS may:
1. Store your professional profile data securely in an encrypted database.
2. Autonomously search and apply for IT jobs on your behalf on supported portals.
3. Process your resume and skills using your chosen LLM provider to generate tailored applications.
4. Send notifications via email and your chosen messaging platform (Telegram or Discord).
5. Retain your data in accordance with the DPDPA 2023 and our Privacy Policy.

You retain the right to access, correct, and delete your data at any time from account settings.
"""


async def record_consent(
    user_id: str,
    ip_address: str,
    user_agent: str,
    consented_to_auto_apply: bool,
    consented_to_llm_processing: bool,
    llm_choice: str,
    db: AsyncSession,
) -> ConsentRecord:
    record = ConsentRecord(
        user_id=user_id,
        consent_version=CURRENT_CONSENT_VERSION,
        ip_address=ip_address,
        user_agent=user_agent,
        consented_to_data_processing=True,
        consented_to_auto_apply=consented_to_auto_apply,
        consented_to_llm_processing=consented_to_llm_processing,
        llm_choice=llm_choice,
        consent_text_hash=sha256(CONSENT_TEXT.encode()).hexdigest(),
    )
    db.add(record)
    await db.commit()
    # IP and user agent stay in the consent record only, not the log stream.
    audit("consent.granted", user_id=user_id, details={
        "consent_version": CURRENT_CONSENT_VERSION,
        "consented_to_auto_apply": consented_to_auto_apply,
        "consented_to_llm_processing": consented_to_llm_processing,
        "llm_choice": llm_choice,
    })
    return record


async def current_consent(user_id: str, db: AsyncSession) -> ConsentRecord | None:
    """The user's latest consent record, or None when they never consented."""
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id)
        .order_by(ConsentRecord.consented_at.desc(), ConsentRecord.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def consent_history(user_id: str, db: AsyncSession) -> list[ConsentRecord]:
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id)
        .order_by(ConsentRecord.consented_at.asc(), ConsentRecord.id.asc())
    )
    return list(result.scalars().all())


def consent_allows(record: ConsentRecord | None, scope: str) -> bool:
    """Every scope needs data processing consent too; no record allows nothing."""
    if record is None or not record.consented_to_data_processing:
        return False
    column = CONSENT_SCOPES.get(scope)
    return column is not None and bool(getattr(record, column))


def _checked_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    wanted = tuple(sorted(set(scopes)))
    unknown = [s for s in wanted if s not in CONSENT_SCOPES]
    if not wanted or unknown:
        raise ValueError(f"scopes must be a non-empty subset of {sorted(CONSENT_SCOPES)}: {unknown}")
    return wanted


def _after(previous: datetime) -> datetime:
    """Now, but never at or before the record being replaced (hosts' clocks can differ)."""
    return max(datetime.now(timezone.utc), previous + timedelta(microseconds=1))


def _withdrawal_row(latest: ConsentRecord, scopes: tuple[str, ...],
                    ip_address: str, user_agent: str) -> ConsentRecord:
    flags = {col: getattr(latest, col) for col in CONSENT_SCOPES.values()}
    flags.update({CONSENT_SCOPES[s]: False for s in scopes})
    return ConsentRecord(
        user_id=latest.user_id, event="withdrawn", ip_address=ip_address,
        user_agent=user_agent, llm_choice=latest.llm_choice,
        consent_version=latest.consent_version, consent_text_hash=latest.consent_text_hash,
        consented_at=_after(latest.consented_at), **flags,
    )


async def withdraw_consent(
    user_id: str, scopes: Iterable[str], ip_address: str, user_agent: str, db: AsyncSession,
) -> Withdrawal:
    """Append a 'withdrawn' row; earlier rows are never changed (DPDP Act s.6(4))."""
    wanted = _checked_scopes(scopes)
    # Serialise withdrawals per user so none copies a stale flag from `latest`.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    latest = await current_consent(user_id, db)
    if latest is None:
        raise NoConsentOnRecord(user_id)
    newly = tuple(s for s in wanted if getattr(latest, CONSENT_SCOPES[s]))
    if not newly:
        return Withdrawal(record=latest, withdrawn=())
    record = _withdrawal_row(latest, newly, ip_address, user_agent)
    db.add(record)
    await db.commit()
    # IP and user agent stay in the consent record only, not the log stream.
    audit("consent.withdrawn", user_id=user_id, details={"scopes": list(newly)})
    return Withdrawal(record=record, withdrawn=newly)
