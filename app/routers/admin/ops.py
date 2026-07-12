from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from app.database import get_db
from app.models.user import User
from app.models.portal_account import SystemPortalAccount
from app.models.admin import AdminRole
from app.dependencies import require_role

router = APIRouter(prefix="/api/admin/ops", tags=["admin-ops"])


@router.get("/dashboard")
async def ops_dashboard(
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.ops_admin)),
    db: AsyncSession = Depends(get_db),
):
    """Live operations dashboard data."""
    total_users = await db.execute(select(func.count(User.id)))
    active_users = await db.execute(select(func.count(User.id)).where(User.is_active == True))
    onboarded = await db.execute(
        select(func.count(User.id)).where(User.onboarding_complete == True)
    )

    portals = await db.execute(select(SystemPortalAccount))
    portal_health = [
        {"portal": p.portal, "health": p.health, "last_crawl": str(p.last_crawl) if p.last_crawl else None}
        for p in portals.scalars().all()
    ]

    pending_skills = await db.execute(
        text("SELECT COUNT(*) FROM skill_taxonomy WHERE status='pending_review'")
    )

    return {
        "users": {
            "total": total_users.scalar(),
            "active": active_users.scalar(),
            "onboarding_complete": onboarded.scalar(),
        },
        "portal_health": portal_health,
        "pending_taxonomy_reviews": pending_skills.scalar(),
    }
