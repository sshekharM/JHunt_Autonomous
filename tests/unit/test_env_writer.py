"""
The Windows installer writes the production .env.
Given a wizard config, when the .env is written, then its security settings
match the app's secure defaults (production, 4h sessions).
"""
from installer.core.env_writer import write_env


def _env(tmp_path) -> dict[str, str]:
    path = write_env({}, str(tmp_path))
    with open(path, encoding="utf-8") as f:
        pairs = (line.split("=", 1) for line in f.read().splitlines() if "=" in line)
        return {k: v for k, v in pairs if not k.startswith("#")}


def test_installer_sets_four_hour_sessions(tmp_path):
    assert _env(tmp_path)["JWT_EXPIRY_HOURS"] == "4"


def test_installer_writes_production_env(tmp_path):
    assert _env(tmp_path)["APP_ENV"] == "production"
