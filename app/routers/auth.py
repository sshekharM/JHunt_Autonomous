import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import OAuthProvider, User
from app.security.audit_log import audit
from app.security.encryption import decrypt, encrypt, sha256_hash
from app.security.rate_limiter import limiter
from app.security.totp import (
    generate_qr_code_base64,
    generate_totp_secret,
    get_totp_uri,
    matched_totp_step,
)
from app.services.auth_service import (
    PENDING_2FA_TTL,
    create_access_token,
    create_pending_2fa_token,
    decode_pending_2fa_token,
    oauth,
)
from app.services.totp_lockout import (
    is_replayed_step,
    lock_seconds_left,
    record_failure,
    record_success,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SUPPORTED_PROVIDERS = {"google", "linkedin", "facebook"}
PENDING_2FA_COOKIE = "pending_2fa"
PENDING_2FA_PATH = "/api/auth/totp"


@router.get("/login/{provider}")
@limiter.limit("20/minute")
async def login(request: Request, provider: str):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    redirect_uri = f"{request.base_url}api/auth/callback/{provider}"
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def callback(request: Request, provider: str, db: AsyncSession = Depends(get_db)):  # noqa: B008 - FastAPI's DI pattern requires the call in the default
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)

    # Fetch user info from provider
    if provider == "google":
        userinfo = token.get("userinfo") or await client.userinfo(token=token)
        email = userinfo["email"]
        sub = userinfo["sub"]
    elif provider == "linkedin":
        resp = await client.get("me", token=token)
        email_resp = await client.get(
            "emailAddress?q=members&projection=(elements*(handle~))", token=token
        )
        userinfo = resp.json()
        sub = userinfo["id"]
        try:
            email = email_resp.json()["elements"][0]["handle~"]["emailAddress"]
        except (KeyError, IndexError):
            raise HTTPException(status_code=400, detail="Could not retrieve email from LinkedIn.")
    elif provider == "facebook":
        resp = await client.get("me?fields=id,name,email,picture", token=token)
        userinfo = resp.json()
        sub = userinfo["id"]
        email = userinfo.get("email", "")

    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by OAuth provider.")

    email_hash = sha256_hash(email.lower())
    result = await db.execute(select(User).where(User.email_hash == email_hash))
    existing_user = result.scalar_one_or_none()

    is_new_user = existing_user is None
    if existing_user is None:
        # New user — create record; onboarding will complete the profile
        user = User(
            id=str(uuid.uuid4()),
            email_hash=email_hash,
            email_encrypted=encrypt(email),
            thumbprint="",
            schema_name="",
            oauth_provider=OAuthProvider(provider),
            oauth_sub=sub,
            totp_secret_encrypted=encrypt(generate_totp_secret()),
            totp_verified=False,
            onboarding_complete=False,
            onboarding_step=1,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        audit("user.created", user_id=user.id, details={"provider": provider})
    else:
        user = existing_user

    if not user.totp_verified:
        return _totp_setup_response(user, email, is_new_user)

    token_str = create_access_token({"sub": user.id})
    response = RedirectResponse(
        url="/dashboard" if user.onboarding_complete else "/onboarding",
        status_code=302,
    )
    response.set_cookie(
        key="access_token",
        value=token_str,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_expiry_hours * 3600,  # cookie and JWT expire together
    )
    audit("auth.login", user_id=user.id, details={"provider": provider})
    return response


def _totp_setup_response(user: User, email: str, is_new_user: bool) -> JSONResponse:
    """TOTP enrolment payload plus the short-lived pending_2fa cookie that /totp/verify requires."""
    uri = get_totp_uri(decrypt(user.totp_secret_encrypted), email)
    qr_b64 = generate_qr_code_base64(uri)
    audit("auth.totp_setup_required", user_id=user.id)
    setup = JSONResponse({
        "action": "totp_setup",
        "user_id": user.id,
        "qr_code_base64": qr_b64,
        "totp_uri": uri,
        "is_new_user": is_new_user,
    })
    setup.set_cookie(
        key=PENDING_2FA_COOKIE, value=create_pending_2fa_token(user.id),
        httponly=True, secure=True, samesite="lax", path=PENDING_2FA_PATH,
        max_age=int(PENDING_2FA_TTL.total_seconds()),
    )
    return setup


async def _pending_2fa_user(pending_2fa: str | None, db: AsyncSession) -> User:
    """User named by a valid pending_2fa cookie; a token for an already-verified user is spent."""
    user_id = decode_pending_2fa_token(pending_2fa)
    # FOR UPDATE: concurrent attempts for one account queue, so counters and steps stay exact;
    # populate_existing so a row already in the session is re-read under the lock, not reused
    result = await db.execute(
        select(User).where(User.id == user_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.totp_verified:
        raise HTTPException(status_code=401, detail="Pending 2FA session already used.")
    if not user.totp_secret_encrypted:  # anonymised: no secret left to check against
        raise HTTPException(status_code=401, detail="No TOTP enrolment for this account.")
    return user


async def _check_totp_code(user: User, code: str, db: AsyncSession) -> None:
    """Refuse locked accounts, bad codes and replayed time steps (CHG-006).

    A failure commits its counter here, before raising. A success only updates
    the counters and leaves the commit to the caller, together with the rest of
    the successful verification.
    """
    now = datetime.now(timezone.utc)
    wait = lock_seconds_left(user, now)
    if wait:
        audit("auth.totp_locked", user_id=user.id)
        raise HTTPException(
            status_code=429, detail="Too many invalid TOTP codes. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    step = matched_totp_step(decrypt(user.totp_secret_encrypted), code, now)
    if step is None or is_replayed_step(user, step):
        record_failure(user, now)
        await db.commit()
        audit("auth.totp_failed", user_id=user.id,
              details={"reason": "invalid" if step is None else "replayed"})
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    record_success(user, step)


class TotpVerifyRequest(BaseModel):
    code: str  # in the body, never the URL, so one-time codes stay out of access logs


@router.post("/totp/verify")
@limiter.limit("10/minute")
async def verify_totp_code(
    request: Request,
    body: TotpVerifyRequest,
    pending_2fa: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),  # noqa: B008 - FastAPI's DI pattern requires the call in the default
):
    user = await _pending_2fa_user(pending_2fa, db)
    await _check_totp_code(user, body.code, db)
    user.totp_verified = True
    await db.commit()
    audit("auth.totp_verified", user_id=user.id)

    token_str = create_access_token({"sub": user.id})
    response = JSONResponse({"ok": True, "redirect": "/onboarding" if not user.onboarding_complete else "/dashboard"})
    response.set_cookie(
        key="access_token", value=token_str, httponly=True,
        secure=True, samesite="lax", max_age=settings.jwt_expiry_hours * 3600,
    )
    response.delete_cookie(
        PENDING_2FA_COOKIE, path=PENDING_2FA_PATH,
        httponly=True, secure=True, samesite="lax",
    )
    return response


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user),  # noqa: B008 - FastAPI's DI pattern requires the call in the default
):
    audit("auth.logout", user_id=user.id)
    response.delete_cookie("access_token")
    return {"ok": True}
