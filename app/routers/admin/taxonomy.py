from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel
from app.database import get_db
from app.models.admin import AdminRole
from app.dependencies import require_role
from app.security.audit_log import audit

router = APIRouter(prefix="/api/admin/taxonomy", tags=["admin-taxonomy"])


class SkillReviewAction(BaseModel):
    skill_id: str
    action: str  # "approve" or "reject"
    category: str = ""


@router.get("/pending")
async def list_pending_skills(
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.content_admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT id, skill_name, category, source, auto_suggested_category FROM skill_taxonomy WHERE status='pending_review'")
    )
    return [
        {"id": r[0], "skill_name": r[1], "category": r[2], "source": r[3], "suggested_category": r[4]}
        for r in result.fetchall()
    ]


@router.post("/review")
async def review_skill(
    data: SkillReviewAction,
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.content_admin)),
    db: AsyncSession = Depends(get_db),
):
    if data.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'.")
    new_status = "active" if data.action == "approve" else "rejected"
    await db.execute(
        text("UPDATE skill_taxonomy SET status=:s, category=COALESCE(NULLIF(:cat,''), category) WHERE id=:id"),
        {"s": new_status, "cat": data.category, "id": data.skill_id},
    )
    await db.commit()
    audit(
        f"admin.taxonomy.skill_{data.action}d",
        admin_id=admin.id,
        details={"skill_id": data.skill_id, "category": data.category},
    )
    return {"ok": True, "status": new_status}
