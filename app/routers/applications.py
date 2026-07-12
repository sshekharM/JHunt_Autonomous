from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.deletion import DeletionMode, execute_deletion
from app.database import get_db, get_tenant_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.application_service import transition_status
from app.tenant_models.application import ApplicationStatus, ApplicationStatusLog, JobApplication
from app.tenant_models.profile import UserPreferences

router = APIRouter(prefix="/api/applications", tags=["applications"])


class PauseRequest(BaseModel):
    minutes: int = 60


class CompanyBlacklistRequest(BaseModel):
    name: str


class TitleBlacklistRequest(BaseModel):
    title: str


class AccountDeletionRequest(BaseModel):
    mode: str


@router.get("/")
async def list_applications(
    application_status: Optional[str] = None,
    portal: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
):
    results = []
    async for tenant_db in get_tenant_db(user.schema_name):
        q = select(JobApplication)
        if application_status:
            try:
                q = q.where(JobApplication.status == ApplicationStatus(application_status))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown status: {application_status}")
        if portal:
            q = q.where(JobApplication.portal == portal)
        q = q.order_by(JobApplication.created_at.desc()).limit(limit).offset(offset)
        rows = await tenant_db.execute(q)
        apps = rows.scalars().all()
        results = [
            {
                "id": a.id,
                "job_title": a.job_title,
                "company": a.company,
                "portal": a.portal,
                "status": a.status.value,
                "match_score": a.match_score,
                "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            }
            for a in apps
        ]
    return results


@router.get("/{application_id}")
async def get_application(
    application_id: str,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(
            select(JobApplication).where(JobApplication.id == application_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")

        history_result = await tenant_db.execute(
            select(ApplicationStatusLog)
            .where(ApplicationStatusLog.application_id == application_id)
            .order_by(ApplicationStatusLog.recorded_at)
        )
        history = history_result.scalars().all()

        return {
            "id": app.id,
            "job_title": app.job_title,
            "company": app.company,
            "portal": app.portal,
            "portal_job_id": app.portal_job_id,
            "status": app.status.value,
            "match_score": app.match_score,
            "failure_reason": app.failure_reason.value if app.failure_reason else None,
            "applied_at": app.applied_at.isoformat() if app.applied_at else None,
            "history": [
                {
                    "from_status": h.from_status,
                    "to_status": h.to_status,
                    "note": h.note,
                    "recorded_at": h.recorded_at.isoformat(),
                }
                for h in history
            ],
        }


@router.post("/{application_id}/withdraw")
async def withdraw_application(
    application_id: str,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        await transition_status(
            application_id=application_id,
            new_status=ApplicationStatus.withdrawn,
            tenant_db=tenant_db,
            note="withdrawn by user",
        )
    return {"ok": True}


@router.post("/pause")
async def pause_auto_apply(
    body: PauseRequest,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            raise HTTPException(status_code=404, detail="Preferences not found.")
        prefs.auto_apply_paused = True
        prefs.pause_until = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
        await tenant_db.commit()
    return {"ok": True, "paused_until": prefs.pause_until.isoformat()}


@router.delete("/pause")
async def resume_auto_apply(
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            raise HTTPException(status_code=404, detail="Preferences not found.")
        prefs.auto_apply_paused = False
        prefs.pause_until = None
        await tenant_db.commit()
    return {"ok": True}


@router.post("/blacklist/company")
async def add_company_blacklist(
    body: CompanyBlacklistRequest,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            raise HTTPException(status_code=404, detail="Preferences not found.")
        bl = list(prefs.company_blacklist or [])
        if body.name not in bl:
            bl.append(body.name)
            prefs.company_blacklist = bl
            await tenant_db.commit()
    return {"ok": True}


@router.delete("/blacklist/company/{name}")
async def remove_company_blacklist(
    name: str,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            raise HTTPException(status_code=404, detail="Preferences not found.")
        prefs.company_blacklist = [c for c in (prefs.company_blacklist or []) if c != name]
        await tenant_db.commit()
    return {"ok": True}


@router.post("/blacklist/title")
async def add_title_blacklist(
    body: TitleBlacklistRequest,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            raise HTTPException(status_code=404, detail="Preferences not found.")
        bl = list(prefs.title_blacklist or [])
        if body.title not in bl:
            bl.append(body.title)
            prefs.title_blacklist = bl
            await tenant_db.commit()
    return {"ok": True}


@router.delete("/blacklist/title/{title}")
async def remove_title_blacklist(
    title: str,
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            raise HTTPException(status_code=404, detail="Preferences not found.")
        prefs.title_blacklist = [t for t in (prefs.title_blacklist or []) if t != title]
        await tenant_db.commit()
    return {"ok": True}


@router.get("/blacklist")
async def get_blacklists(
    user: User = Depends(get_current_user),
):
    async for tenant_db in get_tenant_db(user.schema_name):
        result = await tenant_db.execute(select(UserPreferences))
        prefs = result.scalar_one_or_none()
        if not prefs:
            return {"companies": [], "titles": []}
        return {
            "companies": prefs.company_blacklist or [],
            "titles": prefs.title_blacklist or [],
        }


@router.delete("/account")
async def delete_account(
    body: AccountDeletionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        mode = DeletionMode(body.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown deletion mode: {body.mode}")
    result = await execute_deletion(user=user, mode=mode, db=db)
    return result
