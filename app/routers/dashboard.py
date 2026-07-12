from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from app.database import get_db, get_tenant_db
from app.models.user import User
from app.dependencies import get_current_user
from app.security.encryption import decrypt

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/")
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return curated dashboard data for the logged-in user."""
    stats = {
        "total_applied": 0,
        "shortlisted": 0,
        "rejected": 0,
        "pending_hitl": 0,
        "failed": 0,
        "new_matches": 0,
    }
    profile = {}
    recent_applications = []
    missing_info = []

    async for tenant_db in get_tenant_db(user.schema_name):
        # Stats
        result = await tenant_db.execute(text("""
            SELECT status, COUNT(*) FROM applications GROUP BY status
        """))
        for row in result.fetchall():
            status, count = row
            if status == "applied":
                stats["total_applied"] += count
            elif status == "shortlisted":
                stats["shortlisted"] += count
            elif status == "rejected":
                stats["rejected"] += count
            elif status == "pending_hitl":
                stats["pending_hitl"] += count
            elif status in ("failed_portal_error", "failed_low_match", "failed_missing_info"):
                stats["failed"] += count

        # New matches (not yet applied)
        nm = await tenant_db.execute(text("""
            SELECT COUNT(*) FROM jobs j
            WHERE NOT EXISTS (
                SELECT 1 FROM applications a WHERE a.portal_job_id = j.portal_job_id
            )
        """))
        stats["new_matches"] = nm.scalar() or 0

        # Profile snippet
        p = await tenant_db.execute(text(
            "SELECT full_name_encrypted, city, current_role, years_experience FROM profile LIMIT 1"
        ))
        row = p.first()
        if row:
            profile = {
                "full_name": decrypt(row[0]),
                "city": row[1],
                "current_role": row[2],
                "years_experience": row[3],
            }

        # Recent applications
        apps = await tenant_db.execute(text("""
            SELECT job_title, company, portal, status, applied_at, match_score
            FROM applications ORDER BY created_at DESC LIMIT 10
        """))
        recent_applications = [
            {
                "job_title": r[0], "company": r[1], "portal": r[2],
                "status": r[3], "applied_at": str(r[4]) if r[4] else None,
                "match_score": round(r[5] * 100, 1),
            }
            for r in apps.fetchall()
        ]

        # Missing info prompts
        mi = await tenant_db.execute(text(
            "SELECT field_name, field_label, portal FROM missing_info_log WHERE resolved=false"
        ))
        missing_info = [
            {"field_name": r[0], "label": r[1], "portal": r[2]}
            for r in mi.fetchall()
        ]

    return {
        "profile": profile,
        "stats": stats,
        "recent_applications": recent_applications,
        "missing_info_prompts": missing_info,
    }
