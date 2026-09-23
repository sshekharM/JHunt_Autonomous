"""
Unit tests for the admin crawl trigger (app/routers/admin/crawls.py).
The accepted portals must match the shared crawler registry, so every portal
crawled on the beat schedule can also be triggered manually.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.crawlers.registry import SUPPORTED_PORTALS


def _admin():
    admin = MagicMock()
    admin.id = "admin-1"
    return admin


async def _trigger(portal: str):
    from app.routers.admin import crawls
    task = MagicMock(id="task-1")
    with patch.object(crawls, "crawl_portal") as crawl, patch.object(crawls, "audit"):
        crawl.delay.return_value = task
        result = await crawls.trigger_crawl(portal=portal, admin=_admin())
    return result, crawl


@pytest.mark.asyncio
@pytest.mark.parametrize("portal", SUPPORTED_PORTALS)
async def test_trigger_accepts_every_registry_portal(portal):
    result, crawl = await _trigger(portal)
    crawl.delay.assert_called_once_with(portal)
    assert result == {"ok": True, "task_id": "task-1", "portal": portal}


@pytest.mark.asyncio
async def test_trigger_accepts_portal_case_insensitively():
    result, crawl = await _trigger("Monster")
    crawl.delay.assert_called_once_with("monster")
    assert result["portal"] == "monster"


@pytest.mark.asyncio
async def test_trigger_rejects_unknown_portal_with_400():
    with pytest.raises(HTTPException) as exc:
        await _trigger("myspace")
    assert exc.value.status_code == 400
