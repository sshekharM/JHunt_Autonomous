from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.models.admin import AdminRole
from app.dependencies import require_role
from app.config import settings
from app.security.audit_log import audit

router = APIRouter(prefix="/api/admin/config", tags=["admin-config"])


class SystemConfigUpdate(BaseModel):
    crawl_interval_hours: int | None = None
    crawl_max_concurrency: int | None = None


@router.get("/")
async def get_config(
    admin=Depends(require_role(AdminRole.super_admin)),
):
    return {
        "crawl_interval_hours": settings.crawl_interval_hours,
        "crawl_max_concurrency": settings.crawl_max_concurrency,
        "app_env": settings.app_env,
    }


@router.patch("/")
async def update_config(
    data: SystemConfigUpdate,
    admin=Depends(require_role(AdminRole.super_admin)),
):
    # Runtime config updates — persisted via env / restart in production
    if data.crawl_interval_hours:
        settings.crawl_interval_hours = data.crawl_interval_hours
    if data.crawl_max_concurrency:
        settings.crawl_max_concurrency = data.crawl_max_concurrency
    audit("admin.config_updated", admin_id=admin.id, details=data.model_dump(exclude_none=True))
    return {"ok": True}
