from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, provision_user_schema
from app.models.user import User, OAuthProvider
from app.services.auth_service import oauth, create_access_token, build_user_thumbprint
from app.security.encryption import encrypt, sha256_hash
from app.security.totp import generate_totp_secret, get_totp_uri, generate_qr_code_base64, verify_totp
from app.security.audit_log import audit
from app.security.rate_limiter import limiter
from app.dependencies import get_current_user
import uuid

router = APIRouter(prefix="/api/auth", tags=["auth"])

SUPPORTED_PROVIDERS = {"google", "linkedin", "facebook"}


@router.get("/login/{provider}")
@limiter.limit("20/minute")
async def login(request: Request, provider: str):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    redirect_uri = f"{request.base_url}api/auth/callback/{provider}"
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def callback(request: Request, provider: str, db: AsyncSession = Depends(get_db)):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)

    # Fetch user info from provider
    if provider == "google":
        userinfo = token.get("userinfo") or await client.userinfo(token=token)
        email = userinfo["email"]
        name = userinfo.get("name", "")
        avatar = userinfo.get("picture", "")
        sub = userinfo["sub"]
    elif provider == "linkedin":
        resp = await client.get("me", token=token)
        email_resp = await client.get(
            "emailAddress?q=members&projection=(elements*(handle~))", token=token
        )
        userinfo = resp.json()
        sub = userinfo["id"]
        first = userinfo.get("localizedFirstName", "")
        last = userinfo.get("localizedLastName", "")
        name = f"{first} {last}".strip()
        avatar = ""
        try:
            email = email_resp.json()["elements"][0]["handle~"]["emailAddress"]
        except (KeyError, IndexError):
            raise HTTPException(status_code=400, detail="Could not retrieve email from LinkedIn.")
    elif provider == "facebook":
        resp = await client.get("me?fields=id,name,email,picture", token=token)
        userinfo = resp.json()
        sub = userinfo["id"]
        name = userinfo.get("name", "")
        email = userinfo.get("email", "")
        avatar = userinfo.get("picture", {}).get("data", {}).get("url", "")

    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by OAuth provider.")

    email_hash = sha256_hash(email.lower())
    result = await db.execute(select(User).where(User.email_hash == email_hash))
    user = result.scalar_one_or_none()

    is_new_user = user is None
    if is_new_user:
        # New user — create record; onboarding will complete the profile
        user = User(
            id=str(uuid.uuid4()),
            email_hash=email_hash,
            email_encrypted=encrypt(email),
            thumbprint="",
            schema_name="",
            oauth_provider=OAuthProvider(provider),
            oauth_sub=sub,
            totp_secret=generate_totp_secret(),
            totp_verified=False,
            onboarding_complete=False,
            onboarding_step=1,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        audit("user.created", user_id=user.id, details={"provider": provider})

    if not user.totp_verified:
        # Return TOTP setup info
        uri = get_totp_uri(user.totp_secret, email)
        qr_b64 = generate_qr_code_base64(uri)
        audit("auth.totp_setup_required", user_id=user.id)
        return JSONResponse({
            "action": "totp_setup",
            "user_id": user.id,
            "qr_code_base64": qr_b64,
            "totp_uri": uri,
            "is_new_user": is_new_user,
        })

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
        max_age=3600 * 8,
    )
    audit("auth.login", user_id=user.id, details={"provider": provider})
    return response


@router.post("/totp/verify")
@limiter.limit("10/minute")
async def verify_totp_code(
    request: Request,
    user_id: str,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not verify_totp(user.totp_secret, code):
        audit("auth.totp_failed", user_id=user.id)
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")

    user.totp_verified = True
    await db.commit()
    audit("auth.totp_verified", user_id=user.id)

    token_str = create_access_token({"sub": user.id})
    response = JSONResponse({"ok": True, "redirect": "/onboarding" if not user.onboarding_complete else "/dashboard"})
    response.set_cookie(
        key="access_token", value=token_str, httponly=True,
        secure=True, samesite="lax", max_age=3600 * 8,
    )
    return response


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user),
):
    audit("auth.logout", user_id=user.id)
    response.delete_cookie("access_token")
    return {"ok": True}
