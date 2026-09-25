"""
Characterization tests for app.llm.ollama_client.

No real network calls -- httpx.AsyncClient is replaced with a fake that
records the request it was given and returns a canned response.
"""
from typing import Any
from unittest.mock import patch

import pytest

from app.llm import ollama_client


class _FakeResponse:
    def __init__(self, json_data: Any, raise_exc: Exception | None = None):
        self._json = json_data
        self._raise = raise_exc

    def raise_for_status(self) -> None:
        if self._raise:
            raise self._raise

    def json(self) -> Any:
        return self._json


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse, timeout: float | None = None):
        self.response = response
        self.timeout = timeout
        self.calls: list[dict] = []

    def __call__(self, *args: Any, **kwargs: Any) -> "_FakeAsyncClient":
        self.timeout = kwargs.get("timeout")
        return self

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, json: dict) -> _FakeResponse:
        self.calls.append({"url": url, "json": json})
        return self.response


@pytest.mark.asyncio
async def test_generate_posts_prompt_and_returns_response_text():
    fake_client = _FakeAsyncClient(_FakeResponse({"response": "hello there"}))
    with patch("app.llm.ollama_client.httpx.AsyncClient", fake_client):
        result = await ollama_client.generate("say hi")

    assert result == "hello there"
    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["url"].endswith("/api/generate")
    assert call["json"]["prompt"] == "say hi"
    assert call["json"]["stream"] is False
    assert "system" not in call["json"]


@pytest.mark.asyncio
async def test_generate_includes_system_prompt_when_provided():
    fake_client = _FakeAsyncClient(_FakeResponse({"response": "ok"}))
    with patch("app.llm.ollama_client.httpx.AsyncClient", fake_client):
        await ollama_client.generate("prompt", system_prompt="be terse")

    assert fake_client.calls[0]["json"]["system"] == "be terse"


@pytest.mark.asyncio
async def test_generate_returns_empty_string_when_response_key_missing():
    fake_client = _FakeAsyncClient(_FakeResponse({}))
    with patch("app.llm.ollama_client.httpx.AsyncClient", fake_client):
        result = await ollama_client.generate("prompt")

    assert result == ""


@pytest.mark.asyncio
async def test_generate_propagates_http_error():
    fake_client = _FakeAsyncClient(
        _FakeResponse({}, raise_exc=RuntimeError("upstream 500"))
    )
    with patch("app.llm.ollama_client.httpx.AsyncClient", fake_client):
        with pytest.raises(RuntimeError, match="upstream 500"):
            await ollama_client.generate("prompt")
