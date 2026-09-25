
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin import AdminRole, AdminUser
from app.models.user import User
from app.services.auth_service import decode_access_token, session_user_id


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated."
        )
    user_id = session_user_id(access_token)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    if not user.totp_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="2FA setup required."
        )
    return user


async def get_current_admin(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    payload = decode_access_token(access_token)
    admin_id = payload.get("admin_sub")
    if not admin_id or "purpose" in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an admin token.")

    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found.")
    if not admin.totp_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="2FA setup required.")
    return admin


def require_role(*roles: AdminRole):
    async def checker(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if admin.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{admin.role}' is not authorised for this action.",
            )
        return admin
    return checker
