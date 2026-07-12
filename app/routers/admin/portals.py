from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.portal_account import SystemPortalAccount, PortalAccountHealth
from app.models.admin import AdminRole
from app.dependencies import require_role
from app.security.audit_log import audit

router = APIRouter(prefix="/api/admin/portals", tags=["admin-portals"])


@router.get("/")
async def list_portal_accounts(
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.ops_admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemPortalAccount))
    accounts = result.scalars().all()
    return [
        {
            "id": a.id, "portal": a.portal, "health": a.health,
            "last_login": str(a.last_login) if a.last_login else None,
            "last_crawl": str(a.last_crawl) if a.last_crawl else None,
            "is_active": a.is_active, "notes": a.notes,
        }
        for a in accounts
    ]


@router.post("/{portal}/health")
async def update_portal_health(
    portal: str,
    health: PortalAccountHealth,
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.ops_admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SystemPortalAccount).where(SystemPortalAccount.portal == portal)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Portal account not found.")
    account.health = health
    await db.commit()
    audit("admin.portal_health_updated", admin_id=admin.id, details={"portal": portal, "health": health})
    return {"ok": True}
