"""
Characterization tests for app/crawlers/session_manager.py.
No real Redis or Playwright browser -- everything below the module boundary
is faked. Module-level singleton state (_redis/_browser/_context_pool) is
reset around every test so tests do not leak into each other.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawlers import session_manager
from app.security.encryption import decrypt
from tests.unit.crawler_fakes import FakeContext


class FakeRedis:
    def __init__(self):
        self.store: dict = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def _reset_module_state():
    session_manager._redis = None
    session_manager._playwright = None
    session_manager._browser = None
    session_manager._context_pool = {}
    yield
    session_manager._redis = None
    session_manager._playwright = None
    session_manager._browser = None
    session_manager._context_pool = {}


@pytest.fixture
def fake_redis():
    redis = FakeRedis()
    with patch.object(session_manager, "_get_redis", AsyncMock(return_value=redis)):
        yield redis


@pytest.mark.asyncio
async def test_get_context_returns_pooled_context_when_still_valid():
    async def _valid_pages():
        return []

    pooled = MagicMock()
    pooled.pages = _valid_pages()
    session_manager._context_pool["naukri"] = pooled

    ctx = await session_manager.get_context("naukri")

    assert ctx is pooled


@pytest.mark.asyncio
async def test_get_context_evicts_and_recreates_stale_pooled_context(fake_redis):
    class _Dead:
        @property
        def pages(self):
            raise RuntimeError("context closed")

    session_manager._context_pool["naukri"] = _Dead()
    new_context = FakeContext()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=new_context)

    with patch.object(session_manager, "_get_browser", AsyncMock(return_value=browser)), \
            patch("app.crawlers.session_manager.configure_stealth_context", new=AsyncMock()):
        ctx = await session_manager.get_context("naukri")

    assert ctx is new_context
    assert session_manager._context_pool["naukri"] is new_context


@pytest.mark.asyncio
async def test_get_context_restores_saved_cookies(fake_redis):
    cookies = [{"name": "a", "value": "b"}]
    from app.security.encryption import encrypt

    fake_redis.store["portal_session:naukri"] = encrypt(json.dumps(cookies))
    new_context = FakeContext()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=new_context)

    with patch.object(session_manager, "_get_browser", AsyncMock(return_value=browser)), \
            patch("app.crawlers.session_manager.configure_stealth_context", new=AsyncMock()):
        ctx = await session_manager.get_context("naukri")

    assert await ctx.cookies() == cookies


@pytest.mark.asyncio
async def test_save_session_cookies_encrypts_and_stores(fake_redis):
    context = FakeContext(cookies=[{"name": "sid", "value": "1"}])
    await session_manager.save_session_cookies("naukri", context)

    raw = fake_redis.store["portal_session:naukri"]
    assert json.loads(decrypt(raw)) == [{"name": "sid", "value": "1"}]


@pytest.mark.asyncio
async def test_load_session_cookies_returns_none_when_absent(fake_redis):
    assert await session_manager.load_session_cookies("naukri") is None


@pytest.mark.asyncio
async def test_load_session_cookies_returns_decrypted_list(fake_redis):
    from app.security.encryption import encrypt

    fake_redis.store["portal_session:naukri"] = encrypt(json.dumps([{"a": 1}]))
    assert await session_manager.load_session_cookies("naukri") == [{"a": 1}]


@pytest.mark.asyncio
async def test_load_session_cookies_returns_none_and_warns_on_bad_ciphertext(fake_redis):
    fake_redis.store["portal_session:naukri"] = b"not-valid-fernet-token"
    with patch("app.crawlers.session_manager.logger") as mock_logger:
        result = await session_manager.load_session_cookies("naukri")
    assert result is None
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_clear_session_deletes_redis_key_and_pooled_context(fake_redis):
    context = MagicMock()
    context.close = AsyncMock()
    fake_redis.store["portal_session:naukri"] = b"x"
    session_manager._context_pool["naukri"] = context

    with patch("app.crawlers.session_manager.audit") as mock_audit:
        await session_manager.clear_session("naukri")

    assert "portal_session:naukri" not in fake_redis.store
    assert "naukri" not in session_manager._context_pool
    context.close.assert_awaited_once()
    mock_audit.assert_called_once_with("crawler.session_cleared", details={"portal": "naukri"})


@pytest.mark.asyncio
async def test_clear_session_swallows_context_close_failure_and_continues(fake_redis):
    """Pins the current control flow: a failure closing the pooled context
    must not stop clear_session from removing the pool entry."""
    context = MagicMock()
    context.close = AsyncMock(side_effect=RuntimeError("already gone"))
    session_manager._context_pool["naukri"] = context

    with patch("app.crawlers.session_manager.audit"):
        await session_manager.clear_session("naukri")

    assert "naukri" not in session_manager._context_pool


@pytest.mark.asyncio
async def test_handle_session_expiry_clears_session_and_notifies(fake_redis):
    session_manager._context_pool["naukri"] = MagicMock(close=AsyncMock())
    shared_factory = MagicMock()
    shared_factory.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    shared_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    async def _tenant_gen(_schema):
        yield MagicMock()

    with patch("app.crawlers.session_manager.audit"), \
            patch("app.database.AsyncSessionLocal", shared_factory), \
            patch("app.database.get_tenant_db", _tenant_gen), \
            patch("app.services.notification_service.notify", new=AsyncMock()) as mock_notify:
        await session_manager.handle_session_expiry("naukri", "user-1", "u_abc")

    mock_notify.assert_awaited_once()
    kwargs = mock_notify.call_args.kwargs
    assert kwargs["user_id"] == "user-1"
    assert kwargs["event_type"] == "session_expired"


@pytest.mark.asyncio
async def test_handle_session_expiry_logs_when_notify_fails(fake_redis):
    shared_factory = MagicMock()
    shared_factory.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
    shared_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.crawlers.session_manager.audit"), \
            patch("app.database.AsyncSessionLocal", shared_factory), \
            patch("app.crawlers.session_manager.logger") as mock_logger:
        await session_manager.handle_session_expiry("naukri", "user-1", "u_abc")

    mock_logger.error.assert_called_once()
    assert mock_logger.error.call_args.args[0] == "session_manager.expiry_notify_failed"


@pytest.mark.asyncio
async def test_save_and_load_crawl_state_round_trip(fake_redis):
    await session_manager.save_crawl_state("naukri", {"page": 3})
    state = await session_manager.load_crawl_state("naukri")
    assert state == {"page": 3}


@pytest.mark.asyncio
async def test_load_crawl_state_returns_none_when_absent(fake_redis):
    assert await session_manager.load_crawl_state("naukri") is None


@pytest.mark.asyncio
async def test_shutdown_closes_all_contexts_browser_and_playwright():
    ctx_a = MagicMock(close=AsyncMock())
    ctx_b = MagicMock(close=AsyncMock())
    browser = MagicMock(close=AsyncMock())
    playwright = MagicMock(stop=AsyncMock())
    session_manager._context_pool = {"a": ctx_a, "b": ctx_b}
    session_manager._browser = browser
    session_manager._playwright = playwright

    await session_manager.shutdown()

    ctx_a.close.assert_awaited_once()
    ctx_b.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    assert session_manager._context_pool == {}


@pytest.mark.asyncio
async def test_shutdown_swallows_context_close_failure_and_continues():
    """Pins the current control flow: a failure closing one pooled context
    must not stop shutdown from clearing the pool / stopping the browser."""
    ctx = MagicMock(close=AsyncMock(side_effect=RuntimeError("boom")))
    session_manager._context_pool = {"naukri": ctx}
    session_manager._browser = None
    session_manager._playwright = None

    await session_manager.shutdown()

    assert session_manager._context_pool == {}
