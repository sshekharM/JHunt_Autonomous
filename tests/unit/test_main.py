"""
Pins app.main start-up wiring that the routers rely on: the Windows event-loop
policy and the credentialed CORS set-up the cookie-based session needs.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]


def test_windows_gets_the_selector_event_loop_policy_and_others_keep_the_default():
    probe = "import asyncio, app.main; print(type(asyncio.get_event_loop_policy()).__name__)"
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout.strip().splitlines()[-1]
    # Elsewhere the app must leave the platform default alone (e.g. _UnixDefaultEventLoopPolicy on Linux).
    default = asyncio.DefaultEventLoopPolicy.__name__
    expected = "WindowsSelectorEventLoopPolicy" if sys.platform == "win32" else default
    assert out == expected


def test_cors_allows_credentials_for_the_frontend_only():
    from app.config import settings
    from app.main import app

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert len(cors) == 1
    options = cors[0].kwargs
    assert options["allow_credentials"] is True
    assert options["allow_origins"] == [settings.frontend_url]
