import sys
import asyncio

import structlog
from fastapi import FastAPI, Request

# Python 3.8+ on Windows defaults to ProactorEventLoop which is incompatible
# with some libraries (httpx, uvicorn internals). Force SelectorEventLoop on
# Windows to ensure cross-platform compatibility.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.security.rate_limiter import limiter
from app.routers import auth, onboarding, dashboard, notifications
from app.routers.applications import router as applications_router
from app.routers.admin import users as admin_users
from app.routers.admin import portals as admin_portals
from app.routers.admin import crawls as admin_crawls
from app.routers.admin import taxonomy as admin_taxonomy
from app.routers.admin import config as admin_config
from app.routers.admin import ops as admin_ops

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
)

app = FastAPI(
    title="jH_ANS — Autonomous Job Hunt System",
    description="Autonomous IT job hunting for Indian IT professionals.",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    https_only=settings.is_production,
    same_site="lax",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# User routers
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(applications_router)

# Admin routers
app.include_router(admin_users.router)
app.include_router(admin_portals.router)
app.include_router(admin_crawls.router)
app.include_router(admin_taxonomy.router)
app.include_router(admin_config.router)
app.include_router(admin_ops.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "jH_ANS"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    structlog.get_logger("app").error(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
        stack_trace=traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
