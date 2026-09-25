"""
Characterization tests for app/crawlers/anti_detection.py -- random_viewport
in particular pins the ViewportSize contract (width/height keys) consumed by
Playwright's Browser.new_context(viewport=...).
"""
from app.crawlers.anti_detection import VIEWPORTS, random_user_agent, random_viewport


def test_random_viewport_returns_one_of_the_known_viewports():
    result = random_viewport()
    assert result in VIEWPORTS


def test_random_viewport_has_width_and_height_keys():
    result = random_viewport()
    assert set(result.keys()) == {"width", "height"}
    assert isinstance(result["width"], int)
    assert isinstance(result["height"], int)


def test_random_user_agent_returns_a_non_empty_string():
    assert isinstance(random_user_agent(), str)
    assert random_user_agent() != ""
