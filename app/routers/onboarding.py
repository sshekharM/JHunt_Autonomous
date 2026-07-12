"""
9-step onboarding wizard.
Each step is a PATCH endpoint; frontend POSTs step data sequentially.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from app.database import get_db, get_tenant_db, provision_user_schema
from app.models.user import User
from app.tenant_models.profile import UserProfile, UserPreferences, WFHPreference, LLMChoice, NotificationPlatform
from app.tenant_models.skill import UserSkill
from app.tenant_models.resume import MasterResume
from app.compliance.consent_store import record_consent
from app.security.encryption import encrypt, generate_thumbprint, schema_name_from_thumbprint
from app.security.audit_log import audit
from app.dependencies import get_current_user
from app.services.storage_service import upload_resume
import uuid

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class Step1PersonalData(BaseModel):
    full_name: str
    phone: str
    city: str
    state: str


class Step2ProfessionalData(BaseModel):
    current_role: str
    years_experience: int


class Step3ExperienceData(BaseModel):
    work_history: List[dict]
    education: List[dict]


class Step4PreferencesData(BaseModel):
    desired_roles: List[str]
    preferred_locations: List[str]
    salary_min_lpa: Optional[int] = None
    notice_period_days: int = 0
    wfh_preference: WFHPreference = WFHPreference.any
    match_threshold: float = 0.7
    apply_cap_daily: int = 20
    status_check_frequency_hours: int = 24
    auto_apply_enabled: bool = True
    hitl_enabled: bool = False
    portal_apply_caps: dict = {}


class Step5SkillsData(BaseModel):
    skills: List[dict]  # [{"skill_name": "Python", "proficiency": "expert", "years_used": 5}]


class Step6LLMChoiceData(BaseModel):
    llm_choice: LLMChoice
    data_processing_acknowledged: bool


class Step7NotificationData(BaseModel):
    notification_platform: NotificationPlatform
    telegram_chat_id: Optional[str] = None
    discord_channel_id: Optional[str] = None


class Step9ConsentData(BaseModel):
    consented_to_data_processing: bool
    consented_to_auto_apply: bool
    consented_to_llm_processing: bool


@router.get("/status")
async def get_onboarding_status(user: User = Depends(get_current_user)):
    return {
        "step": user.onboarding_step,
        "complete": user.onboarding_complete,
        "thumbprint": user.thumbprint if user.thumbprint else None,
    }


@router.post("/step/1")
async def step1_personal(
    request: Request,
    data: Step1PersonalData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Collect personal info and generate immutable thumbprint."""
    # Derive thumbprint from email + phone
    from app.security.encryption import decrypt
    email = decrypt(user.email_encrypted)
    thumbprint, schema_name = schema_name_from_thumbprint.__module__ and (
        generate_thumbprint(email, data.phone),
        schema_name_from_thumbprint(generate_thumbprint(email, data.phone)),
    )

    # Check thumbprint uniqueness
    existing = await db.execute(select(User).where(User.thumbprint == thumbprint, User.id != user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email+phone combination already exists.")

    user.thumbprint = thumbprint
    user.schema_name = schema_name

    # Provision per-user schema
    await provision_user_schema(schema_name)

    # Create profile in tenant schema
    async for tenant_db in get_tenant_db(schema_name):
        profile = UserProfile(
            full_name_encrypted=encrypt(data.full_name),
            phone_encrypted=encrypt(data.phone),
            city=data.city,
            state=data.state,
            current_role="",
            years_experience=0,
            work_history=[],
            education=[],
        )
        tenant_db.add(profile)
        await tenant_db.commit()

    user.onboarding_step = 2
    await db.commit()
    audit("onboarding.step1_complete", user_id=user.id)
    return {
        "ok": True,
        "step": 2,
        "thumbprint": thumbprint,
        "thumbprint_notice": (
            "Your identity thumbprint has been generated from your email and phone number. "
            "This thumbprint is permanent and cannot be changed after signup."
        ),
    }


@router.post("/step/2")
async def step2_professional(
    data: Step2ProfessionalData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(text("SELECT id FROM profile LIMIT 1"))
        row = result.first()
        if row:
            await tenant_db.execute(
                text("UPDATE profile SET current_role=:role, years_experience=:yoe WHERE id=:id"),
                {"role": data.current_role, "yoe": data.years_experience, "id": row[0]},
            )
            await tenant_db.commit()
    user.onboarding_step = 3
    await db.commit()
    audit("onboarding.step2_complete", user_id=user.id)
    return {"ok": True, "step": 3}


@router.post("/step/3")
async def step3_experience(
    data: Step3ExperienceData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import json
    async for tenant_db in get_tenant_db(user.schema_name):
        await tenant_db.execute(
            text("UPDATE profile SET work_history=:wh, education=:edu"),
            {
                "wh": json.dumps(data.work_history),
                "edu": json.dumps(data.education),
            },
        )
        await tenant_db.commit()
    user.onboarding_step = 4
    await db.commit()
    audit("onboarding.step3_complete", user_id=user.id)
    return {"ok": True, "step": 4}


@router.post("/step/4")
async def step4_preferences(
    data: Step4PreferencesData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        prefs = UserPreferences(
            desired_roles=data.desired_roles,
            preferred_locations=data.preferred_locations,
            salary_min_lpa=data.salary_min_lpa,
            notice_period_days=data.notice_period_days,
            wfh_preference=data.wfh_preference,
            match_threshold=data.match_threshold,
            apply_cap_daily=data.apply_cap_daily,
            status_check_frequency_hours=data.status_check_frequency_hours,
            auto_apply_enabled=data.auto_apply_enabled,
            hitl_enabled=data.hitl_enabled,
            portal_apply_caps=data.portal_apply_caps,
        )
        tenant_db.add(prefs)
        await tenant_db.commit()
    user.onboarding_step = 5
    await db.commit()
    audit("onboarding.step4_complete", user_id=user.id)
    return {"ok": True, "step": 5}


@router.post("/step/5")
async def step5_skills(
    data: Step5SkillsData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        for s in data.skills:
            skill = UserSkill(
                skill_name=s["skill_name"],
                proficiency=s.get("proficiency", "intermediate"),
                years_used=s.get("years_used"),
            )
            tenant_db.add(skill)
        await tenant_db.commit()
    user.onboarding_step = 6
    await db.commit()
    audit("onboarding.step5_complete", user_id=user.id)
    return {"ok": True, "step": 6}


@router.post("/step/5/resume")
async def step5_resume_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF resumes are accepted.")
    contents = await file.read()
    minio_key = await upload_resume(user.schema_name, contents, file.filename)
    async for tenant_db in get_tenant_db(user.schema_name):
        resume = MasterResume(minio_key=minio_key, original_filename=file.filename or "resume.pdf")
        tenant_db.add(resume)
        await tenant_db.commit()
    audit("onboarding.resume_uploaded", user_id=user.id, resource=minio_key)
    return {"ok": True, "minio_key": minio_key}


@router.post("/step/6")
async def step6_llm_choice(
    data: Step6LLMChoiceData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.data_processing_acknowledged:
        raise HTTPException(status_code=400, detail="You must acknowledge the data processing notice.")
    async for tenant_db in get_tenant_db(user.schema_name):
        await tenant_db.execute(
            text("UPDATE preferences SET llm_choice=:choice"),
            {"choice": data.llm_choice.value},
        )
        await tenant_db.commit()
    user.onboarding_step = 7
    await db.commit()
    audit("onboarding.step6_complete", user_id=user.id, details={"llm": data.llm_choice})
    return {"ok": True, "step": 7}


@router.post("/step/7")
async def step7_notifications(
    data: Step7NotificationData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        await tenant_db.execute(
            text(
                "UPDATE preferences SET notification_platform=:p, "
                "telegram_chat_id=:tg, discord_channel_id=:dc"
            ),
            {
                "p": data.notification_platform.value,
                "tg": data.telegram_chat_id,
                "dc": data.discord_channel_id,
            },
        )
        await tenant_db.commit()
    user.onboarding_step = 8
    await db.commit()
    audit("onboarding.step7_complete", user_id=user.id, details={"platform": data.notification_platform})
    return {"ok": True, "step": 8}


@router.post("/step/9")
async def step9_consent(
    request: Request,
    data: Step9ConsentData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.consented_to_data_processing:
        raise HTTPException(status_code=400, detail="Consent to data processing is required.")

    async for tenant_db in get_tenant_db(user.schema_name):
        prefs_result = await tenant_db.execute(text("SELECT llm_choice FROM preferences LIMIT 1"))
        row = prefs_result.first()
        llm_choice = row[0] if row else "self_hosted"

    await record_consent(
        user_id=user.id,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
        consented_to_auto_apply=data.consented_to_auto_apply,
        consented_to_llm_processing=data.consented_to_llm_processing,
        llm_choice=llm_choice,
        db=db,
    )

    user.onboarding_complete = True
    user.onboarding_step = 9
    await db.commit()
    audit("onboarding.complete", user_id=user.id)
    return {"ok": True, "redirect": "/dashboard"}
