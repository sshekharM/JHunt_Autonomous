from fastapi import APIRouter, Depends, HTTPException
from app.models.admin import AdminRole
from app.dependencies import require_role
from app.security.ip_allowlist import require_server_ip
from app.crawlers.registry import is_supported
from app.tasks.crawl_jobs import crawl_portal
from app.security.audit_log import audit

router = APIRouter(
    prefix="/api/admin/crawls", tags=["admin-crawls"],
    dependencies=[Depends(require_server_ip)],
)


@router.post("/{portal}/trigger")
async def trigger_crawl(
    portal: str,
    admin=Depends(require_role(AdminRole.super_admin, AdminRole.ops_admin)),
):
    if not is_supported(portal):
        raise HTTPException(status_code=400, detail=f"Unknown portal: {portal}")
    portal = portal.lower()
    task = crawl_portal.delay(portal)
    audit("admin.crawl_triggered", admin_id=admin.id, details={"portal": portal, "task_id": task.id})
    return {"ok": True, "task_id": task.id, "portal": portal}
