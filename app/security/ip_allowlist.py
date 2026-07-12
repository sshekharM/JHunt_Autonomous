from fastapi import Request, HTTPException, status
from app.config import settings


def require_server_ip(request: Request) -> None:
    """
    Dependency that restricts access to system portal account endpoints
    to the configured server IPs only.
    """
    client_ip = request.client.host if request.client else ""
    if client_ip not in settings.allowed_ip_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to authorised server IPs.",
        )
