"""Docker compose operations for jH_ANS installer."""
import os
import sys
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error

# Source docker-compose files relative to this installer
_INSTALLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_INSTALLER_DIR)

COMPOSE_FILES = ["docker-compose.yml"]
if sys.platform == "win32":
    COMPOSE_FILES.append("docker-compose.windows.yml")

HEALTH_URL = "http://localhost:8000/health"
HEALTH_TIMEOUT = 120  # seconds


def _copy_compose_files(install_dir: str) -> list:
    """Copy docker-compose files to install_dir. Return list of copied paths."""
    copied = []
    for fname in COMPOSE_FILES:
        src = os.path.join(_PROJECT_ROOT, fname)
        dst = os.path.join(install_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            copied.append(dst)
        else:
            # Try relative to cwd (when running bundled)
            src_cwd = os.path.join(os.getcwd(), fname)
            if os.path.exists(src_cwd):
                shutil.copy2(src_cwd, dst)
                copied.append(dst)
    return copied


def _build_compose_cmd(install_dir: str, subcmd: list) -> list:
    cmd = ["docker", "compose"]
    for fname in COMPOSE_FILES:
        path = os.path.join(install_dir, fname)
        if os.path.exists(path):
            cmd += ["-f", fname]
    cmd += subcmd
    return cmd


def _stream_process(cmd: list, cwd: str, log_callback, encoding="utf-8"):
    """Run cmd, stream stdout+stderr lines to log_callback. Return returncode."""
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding=encoding, errors="replace"
        )
        for line in proc.stdout:
            log_callback(line.rstrip())
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        log_callback("ERROR: docker command not found. Is Docker installed and on PATH?")
        return 1
    except Exception as e:
        log_callback(f"ERROR: {e}")
        return 1


def _wait_for_health(progress_callback, log_callback) -> bool:
    """Poll health endpoint until ready or timeout."""
    log_callback("Waiting for jH_ANS API to become ready...")
    deadline = time.time() + HEALTH_TIMEOUT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        elapsed = int(time.time() - (deadline - HEALTH_TIMEOUT))
        pct = min(90 + int(elapsed / HEALTH_TIMEOUT * 10), 99)
        progress_callback(pct, f"Waiting for services to be ready... ({elapsed}s)")
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
                if resp.status == 200:
                    log_callback(f"Health check passed after {elapsed}s.")
                    return True
        except Exception:
            pass
        time.sleep(3)
    log_callback(f"Health check timed out after {HEALTH_TIMEOUT}s.")
    return False


def run_install(install_dir: str, progress_callback, log_callback) -> bool:
    """
    Full install sequence:
      1. Copy compose files
      2. docker compose pull
      3. docker compose up -d
      4. Poll /health
    progress_callback(pct: int, message: str)
    log_callback(line: str)
    Returns True on success.
    """
    os.makedirs(install_dir, exist_ok=True)

    # Step 1 — copy files
    progress_callback(2, "Copying configuration files...")
    log_callback("Copying Docker Compose files to install directory...")
    copied = _copy_compose_files(install_dir)
    if not copied:
        log_callback(
            "WARNING: No docker-compose.yml found in project root. "
            "Place docker-compose.yml in the install directory manually if needed."
        )
    else:
        for p in copied:
            log_callback(f"Copied: {p}")

    # Copy .env if already written
    env_src = os.path.join(install_dir, ".env")
    if os.path.exists(env_src):
        log_callback(f".env already present at {env_src}")

    # Step 2 — pull
    progress_callback(5, "Pulling Docker images (this may take several minutes)...")
    log_callback("\n--- docker compose pull ---")
    pull_cmd = _build_compose_cmd(install_dir, ["pull"])
    rc = _stream_process(pull_cmd, install_dir, log_callback)
    if rc != 0:
        log_callback(f"\nERROR: docker compose pull failed (exit {rc})")
        return False

    # Step 3 — up
    progress_callback(60, "Starting services...")
    log_callback("\n--- docker compose up -d ---")
    up_cmd = _build_compose_cmd(install_dir, ["up", "-d"])
    rc = _stream_process(up_cmd, install_dir, log_callback)
    if rc != 0:
        log_callback(f"\nERROR: docker compose up -d failed (exit {rc})")
        return False

    # Step 4 — health
    progress_callback(80, "Waiting for services to be ready...")
    healthy = _wait_for_health(progress_callback, log_callback)
    if not healthy:
        log_callback(
            "WARNING: Services did not respond on /health within timeout. "
            "They may still be starting — open http://localhost:8000 in a moment."
        )

    progress_callback(100, "Installation complete!")
    return True
