"""
Playwright browser pool + Redis-backed session persistence.
System portal accounts use this; user personal sessions use separate contexts.
"""
import json
import asyncio
from typing import Optional, Dict
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright
import redis.asyncio as aioredis
from app.config import settings
from app.security.encryption import encrypt, decrypt
from app.crawlers.anti_detection import (
    random_user_agent, random_viewport, configure_stealth_context
)
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("crawlers.session_manager")

_redis: Optional[aioredis.Redis] = None
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_context_pool: Dict[str, BrowserContext] = {}
_pool_lock = asyncio.Lock()


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(settings.redis_url, decode_responses=False)
    return _redis


async def _get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None or not _browser.is_connected():
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
    return _browser


async def get_context(portal: str) -> BrowserContext:
    """
    Get or create a Playwright browser context for a system portal account.
    Restores cookies from Redis if a saved session exists.
    """
    async with _pool_lock:
        if portal in _context_pool:
            ctx = _context_pool[portal]
            # Check if still valid
            try:
                await ctx.pages  # will throw if closed
                return ctx
            except Exception:
                del _context_pool[portal]

        browser = await _get_browser()
        context = await browser.new_context(
            user_agent=random_user_agent(),
            viewport=random_viewport(),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        await configure_stealth_context(context)

        # Restore saved cookies
        cookies = await load_session_cookies(portal)
        if cookies:
            await context.add_cookies(cookies)
            logger.info("session_manager.cookies_restored", portal=portal)

        _context_pool[portal] = context
        return context


async def save_session_cookies(portal: str, context: BrowserContext) -> None:
    """Persist session cookies to Redis (Fernet-encrypted)."""
    redis = await _get_redis()
    cookies = await context.cookies()
    serialised = json.dumps(cookies)
    encrypted = encrypt(serialised)
    await redis.set(f"portal_session:{portal}", encrypted, ex=86400 * 7)  # 7-day TTL
    logger.info("session_manager.cookies_saved", portal=portal, cookie_count=len(cookies))


async def load_session_cookies(portal: str) -> Optional[list]:
    """Load and decrypt session cookies from Redis."""
    redis = await _get_redis()
    raw = await redis.get(f"portal_session:{portal}")
    if not raw:
        return None
    try:
        decrypted = decrypt(raw)
        return json.loads(decrypted)
    except Exception as exc:
        logger.warning("session_manager.cookie_load_failed", portal=portal, error=str(exc))
        return None


async def clear_session(portal: str) -> None:
    """Remove saved session for a portal (called on session expiry)."""
    redis = await _get_redis()
    await redis.delete(f"portal_session:{portal}")
    if portal in _context_pool:
        try:
            await _context_pool[portal].close()
        except Exception:
            pass
        del _context_pool[portal]
    audit("crawler.session_cleared", details={"portal": portal})


async def save_crawl_state(portal: str, state: dict) -> None:
    """Save crawler progress state for resumption after session drop."""
    redis = await _get_redis()
    await redis.set(f"crawl_state:{portal}", json.dumps(state), ex=3600 * 24)


async def load_crawl_state(portal: str) -> Optional[dict]:
    """Load saved crawler state."""
    redis = await _get_redis()
    raw = await redis.get(f"crawl_state:{portal}")
    return json.loads(raw) if raw else None


async def shutdown() -> None:
    """Gracefully close all browser contexts and the browser."""
    for ctx in _context_pool.values():
        try:
            await ctx.close()
        except Exception:
            pass
    _context_pool.clear()
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
