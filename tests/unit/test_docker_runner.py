"""
Installer health check (installer/core/docker_runner.py): it must poll the
endpoint the API actually serves, and a timeout must say why it failed.
"""
import urllib.error
from unittest.mock import MagicMock, patch

from installer.core import docker_runner


def test_health_url_targets_the_api_health_route():
    # app/main.py serves GET /api/health; /health 404s, so the old check never passed.
    assert docker_runner.HEALTH_URL == "http://localhost:8000/api/health"


def _ok_response():
    resp = MagicMock(status=200)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_wait_for_health_succeeds_on_200():
    log = MagicMock()
    with patch.object(docker_runner.urllib.request, "urlopen", return_value=_ok_response()) as urlopen, \
            patch.object(docker_runner.time, "sleep"):
        assert docker_runner._wait_for_health(MagicMock(), log) is True
    assert urlopen.call_args.args[0] == docker_runner.HEALTH_URL


def test_wait_for_health_times_out_reporting_last_error():
    log = MagicMock()
    clock = iter([0, 0, 1, 1, 200, 200])  # deadline computed, one attempt, then past deadline
    with patch.object(docker_runner.urllib.request, "urlopen", side_effect=urllib.error.URLError("refused")), \
            patch.object(docker_runner.time, "time", side_effect=lambda: next(clock)), \
            patch.object(docker_runner.time, "sleep"):
        assert docker_runner._wait_for_health(MagicMock(), log) is False
    assert "refused" in log.call_args.args[0]


def test_wait_for_health_does_not_swallow_unexpected_errors():
    with patch.object(docker_runner.urllib.request, "urlopen", side_effect=ValueError("bad url")), \
            patch.object(docker_runner.time, "sleep"):
        try:
            docker_runner._wait_for_health(MagicMock(), MagicMock())
        except ValueError:
            return
    raise AssertionError("ValueError should propagate")


def _compose_files_on(platform: str) -> list:
    import importlib
    with patch("sys.platform", platform):
        module = importlib.reload(docker_runner)
        files = list(module.COMPOSE_FILES)
    importlib.reload(docker_runner)
    return files


def test_windows_adds_its_compose_override():
    assert _compose_files_on("win32") == ["docker-compose.yml", "docker-compose.windows.yml"]


def test_other_platforms_use_base_compose_file_only():
    assert _compose_files_on("linux") == ["docker-compose.yml"]


def test_stream_process_streams_decoded_lines():
    proc = MagicMock(stdout=["line one\n", "line two\n"], returncode=0)
    log = MagicMock()
    with patch.object(docker_runner.subprocess, "Popen", return_value=proc) as popen:
        docker_runner._stream_process(["docker", "ps"], "/tmp", log)
    assert popen.call_args.kwargs["text"] is True  # lines are str, not bytes
    assert [c.args[0] for c in log.call_args_list][:2] == ["line one", "line two"]


def test_wait_for_health_stops_exactly_at_deadline():
    clock = iter([0, docker_runner.HEALTH_TIMEOUT] + [docker_runner.HEALTH_TIMEOUT + 1] * 5)
    with patch.object(docker_runner.urllib.request, "urlopen", side_effect=urllib.error.URLError("x")) as urlopen, \
            patch.object(docker_runner.time, "time", side_effect=lambda: next(clock)), \
            patch.object(docker_runner.time, "sleep"):
        assert docker_runner._wait_for_health(MagicMock(), MagicMock()) is False
    urlopen.assert_not_called()
