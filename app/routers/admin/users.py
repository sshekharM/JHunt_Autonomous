from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.admin import AdminRole
from app.dependencies import require_role
from app.security.audit_log import audit

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.get("/")
async def list_users(
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.support_admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            User.id, User.email_hash, User.thumbprint, User.oauth_provider,
            User.is_active, User.onboarding_complete, User.tier, User.created_at,
        )
    )
    return [
        {
            "id": r[0], "email_hash": r[1], "thumbprint": r[2],
            "oauth_provider": r[3], "is_active": r[4],
            "onboarding_complete": r[5], "tier": r[6],
            "created_at": str(r[7]),
        }
        for r in result.fetchall()
    ]


@router.post("/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.support_admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = False
    await db.commit()
    audit("admin.user_suspended", admin_id=admin.id, resource=user_id)
    return {"ok": True}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin=Depends(require_role(AdminRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    await db.delete(user)
    await db.commit()
    audit("admin.user_deleted", admin_id=admin.id, resource=user_id)
    return {"ok": True}
