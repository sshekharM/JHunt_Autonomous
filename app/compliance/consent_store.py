from datetime import datetime, timezone
from hashlib import sha256
from sqlalchemy.ext.asyncio import AsyncSession
from app.compliance.dpdpa import ConsentRecord


CURRENT_CONSENT_VERSION = "1.0"

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
    return record
