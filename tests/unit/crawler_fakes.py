"""
Shared fake Playwright / httpx primitives for crawler characterization tests.
Not a test module itself (no test_* functions) -- imported by the per-portal
test_*_crawler.py files under tests/unit/.
"""
from __future__ import annotations

from typing import Any, Optional


class FakeElement:
    """Fake Playwright ElementHandle."""

    def __init__(self, text: str = "", attrs: Optional[dict] = None, children: Optional[dict] = None):
        self.text = text
        self.attrs = attrs or {}
        self.children = children or {}
        self.filled: Optional[str] = None
        self.uploaded: Optional[str] = None
        self.selected: Optional[str] = None
        self.clicked = False

    async def inner_text(self) -> str:
        return self.text

    async def get_attribute(self, name: str) -> Optional[str]:
        return self.attrs.get(name)

    async def query_selector(self, sel: str):
        v = self.children.get(sel)
        if isinstance(v, list):
            return v[0] if v else None
        return v

    async def query_selector_all(self, sel: str) -> list:
        v = self.children.get(sel, [])
        return v if isinstance(v, list) else [v]

    async def click(self) -> None:
        self.clicked = True

    async def fill(self, value: Any) -> None:
        self.filled = value

    async def set_input_files(self, path: str) -> None:
        self.uploaded = path

    async def select_option(self, label: Optional[str] = None) -> None:
        self.selected = label


class FakeNav:
    def __init__(self, url: str):
        self.url = url


class FakeNavCtx:
    """Fake for `async with page.expect_navigation() as nav_info`."""

    def __init__(self, url: str):
        self._url = url

    async def __aenter__(self):
        async def _value() -> FakeNav:
            return FakeNav(self._url)

        self.value = _value()
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakePage:
    """Fake Playwright Page."""

    def __init__(
        self,
        url: str = "",
        selectors: Optional[dict] = None,
        contents: str = "",
        raise_on_goto: Optional[Exception] = None,
        nav_url: str = "",
    ):
        self.url = url
        self.selectors = selectors or {}
        self._contents = contents
        self.closed = False
        self.filled_selectors: dict = {}
        self.clicked: list = []
        self.raise_on_goto = raise_on_goto
        self._nav_url = nav_url

    async def goto(self, url: str, **kwargs: Any) -> None:
        if self.raise_on_goto:
            raise self.raise_on_goto
        self.url = url

    async def wait_for_load_state(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def wait_for_selector(self, sel: str, **kwargs: Any):
        el = self.selectors.get(sel)
        if el is None:
            raise TimeoutError(f"selector not found: {sel}")
        return el

    async def query_selector(self, sel: str):
        v = self.selectors.get(sel)
        if isinstance(v, list):
            return v[0] if v else None
        return v

    async def query_selector_all(self, sel: str) -> list:
        v = self.selectors.get(sel, [])
        return v if isinstance(v, list) else [v]

    async def click(self, sel: str) -> None:
        self.clicked.append(sel)

    async def type(self, sel: str, char: str, delay: int = 0) -> None:
        return None

    async def fill(self, sel: str, value: Any) -> None:
        self.filled_selectors[sel] = value

    async def content(self) -> str:
        return self._contents

    async def evaluate(self, expr: str) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    def expect_navigation(self, timeout: Optional[int] = None) -> FakeNavCtx:
        return FakeNavCtx(self._nav_url)


class ClickNavPage(FakePage):
    """FakePage variant where clicking navigates the page (post-submit
    redirect), since login()/apply() flows check `page.url` after a click
    rather than after goto()."""

    def __init__(self, url_after_click: str, **kwargs: Any):
        super().__init__(**kwargs)
        self._url_after_click = url_after_click

    async def click(self, sel: str) -> None:
        await super().click(sel)
        self.url = self._url_after_click


class FakeContext:
    """Fake Playwright BrowserContext."""

    def __init__(self, pages_to_return: Optional[list] = None, cookies: Optional[list] = None):
        self._pages_queue = list(pages_to_return or [])
        self._cookies = list(cookies or [])

    async def new_page(self) -> FakePage:
        if self._pages_queue:
            return self._pages_queue.pop(0)
        return FakePage()

    async def cookies(self) -> list:
        return self._cookies

    async def add_cookies(self, cookies: list) -> None:
        self._cookies.extend(cookies)


class FakeResponse:
    """Fake httpx.Response."""

    def __init__(self, status_code: int = 200, text: str = "", json_data: Any = None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self) -> Any:
        return self._json


class FakeAsyncClient:
    """Fake httpx.AsyncClient, used as an async context manager."""

    def __init__(self, response: Optional[FakeResponse] = None, raise_exc: Optional[Exception] = None):
        self._response = response
        self._raise = raise_exc

    def __call__(self, *args: Any, **kwargs: Any) -> "FakeAsyncClient":
        return self

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        if self._raise:
            raise self._raise
        return self._response
