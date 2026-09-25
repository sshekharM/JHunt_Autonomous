from fastapi import HTTPException, Request, status

from app.config import settings


def require_server_ip(request: Request) -> None:
    """Restrict a route to callers whose IP is listed in ``ALLOWED_IPS``.

    Attached as a router-level dependency on every ``/api/admin`` router, so it
    runs before admin authentication: a disallowed IP gets 403 even without a
    session.

    Behaviour is fail-closed:
    - ``ALLOWED_IPS`` is an exact-match, comma-separated list (no CIDR/wildcards).
    - An empty (or all-blank) ``ALLOWED_IPS`` denies every request.
    - A request with no client address is always denied.

    The IP checked is ``request.client.host`` as seen by the ASGI server. Behind
    a reverse proxy it is the proxy's address unless uvicorn is configured to
    trust the proxy's forwarded headers (``--forwarded-allow-ips``).
    """
    client_ip = request.client.host if request.client else ""
    allowed = settings.allowed_ip_list
    if not client_ip or client_ip not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to authorised server IPs.",
        )
