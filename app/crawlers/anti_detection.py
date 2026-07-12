"""
Anti-detection measures for portal crawling.
Simulates human-like browsing behaviour to avoid bot detection.
"""
import asyncio
import random
from typing import Optional
from playwright.async_api import Page, BrowserContext

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
]

# Per-portal request rate limits (seconds between requests)
PORTAL_RATE_LIMITS = {
    "naukri": (3.0, 7.0),
    "linkedin": (4.0, 10.0),
    "glassdoor": (3.0, 8.0),
    "indeed": (2.0, 6.0),
    "default": (2.0, 5.0),
}


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def random_viewport() -> dict:
    return random.choice(VIEWPORTS)


async def human_delay(portal: str = "default") -> None:
    """Wait a randomised human-like delay appropriate for the portal."""
    lo, hi = PORTAL_RATE_LIMITS.get(portal, PORTAL_RATE_LIMITS["default"])
    await asyncio.sleep(random.uniform(lo, hi))


async def micro_delay() -> None:
    """Short pause to simulate reading/thinking time."""
    await asyncio.sleep(random.uniform(0.3, 1.2))


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text character-by-character with random delays."""
    await page.click(selector)
    await micro_delay()
    for char in text:
        await page.type(selector, char, delay=random.randint(60, 180))
    await micro_delay()


async def random_scroll(page: Page) -> None:
    """Scroll to a random position to simulate reading."""
    scroll_y = random.randint(200, 800)
    await page.evaluate(f"window.scrollBy(0, {scroll_y})")
    await asyncio.sleep(random.uniform(0.5, 1.5))


async def configure_stealth_context(context: BrowserContext) -> None:
    """Apply stealth settings to a Playwright browser context."""
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)
