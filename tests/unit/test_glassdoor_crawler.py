"""Unit tests for GlassdoorCrawler card parsing."""
import pytest

from app.crawlers.glassdoor import GlassdoorCrawler


class FakeElement:
    def __init__(self, text: str = "", attr: dict | None = None):
        self._text = text
        self._attr = attr or {}

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        return self._attr.get(name)


class FakeCard:
    """A job-card element whose selectors can be individually stubbed."""

    def __init__(self, elements: dict[str, FakeElement | None]):
        self._elements = elements

    async def query_selector(self, selector: str):
        for key, el in self._elements.items():
            if key in selector:
                return el
        return None


@pytest.mark.asyncio
async def test_parse_card_with_no_location_falls_back_to_search_location():
    card = FakeCard(
        {
            "jobLink": FakeElement(text="Backend Engineer", attr={"href": "/job/123"}),
            "jobHeader": FakeElement(text="Acme Corp"),
            "loc": None,
        }
    )

    crawler = GlassdoorCrawler()
    job = await crawler._parse_card(card, location="Bengaluru")

    assert job is not None
    assert job.title == "Backend Engineer"
    assert job.location == "Bengaluru"
