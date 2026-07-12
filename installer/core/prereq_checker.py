"""Prerequisite checks for jH_ANS installer."""
import socket
import subprocess
import shutil
import os
import sys


REQUIRED_PORTS = [
    (5432, "PostgreSQL"),
    (6379, "Redis"),
    (9000, "MinIO"),
    (8000, "jH_ANS API"),
]


def _port_available(port: int) -> bool:
    """Return True if the port is not currently bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", port))
        # If connection succeeds, port is in use → not available
        return result != 0


def _check_docker_installed() -> dict:
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return {"name": "Docker installed", "status": "ok", "message": version}
        return {"name": "Docker installed", "status": "fail",
                "message": "docker --version returned non-zero exit code"}
    except FileNotFoundError:
        return {"name": "Docker installed", "status": "fail",
                "message": "Docker not found. Please install Docker Desktop."}
    except Exception as e:
        return {"name": "Docker installed", "status": "fail", "message": str(e)}


def _check_docker_running() -> dict:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return {"name": "Docker daemon running", "status": "ok",
                    "message": "Docker daemon is responsive"}
        return {"name": "Docker daemon running", "status": "fail",
                "message": "Docker daemon not running. Start Docker Desktop."}
    except FileNotFoundError:
        return {"name": "Docker daemon running", "status": "fail",
                "message": "Docker not installed"}
    except subprocess.TimeoutExpired:
        return {"name": "Docker daemon running", "status": "fail",
                "message": "Docker info timed out — daemon may be starting"}
    except Exception as e:
        return {"name": "Docker daemon running", "status": "fail", "message": str(e)}


def _check_port(port: int, service: str) -> dict:
    name = f"Port {port} ({service})"
    available = _port_available(port)
    if available:
        return {"name": name, "status": "ok", "message": "Available"}
    else:
        return {"name": name, "status": "warn",
                "message": f"Port {port} is in use — may conflict with {service}"}


def _check_disk_space(path: str = None) -> dict:
    """Check available disk space. Requires >= 10 GB."""
    if path is None:
        if sys.platform == "win32":
            path = "C:\\"
        else:
            path = "/"
    try:
        stat = shutil.disk_usage(path)
        free_gb = stat.free / (1024 ** 3)
        if free_gb >= 10:
            return {"name": "Disk space", "status": "ok",
                    "message": f"{free_gb:.1f} GB free (10 GB required)"}
        elif free_gb >= 5:
            return {"name": "Disk space", "status": "warn",
                    "message": f"Only {free_gb:.1f} GB free — 10 GB recommended"}
        else:
            return {"name": "Disk space", "status": "fail",
                    "message": f"Insufficient disk space: {free_gb:.1f} GB free (need 10 GB)"}
    except Exception as e:
        return {"name": "Disk space", "status": "warn", "message": f"Could not check: {e}"}


def check_all(install_path: str = None) -> list:
    """Return list of {name, status: ok|warn|fail, message} dicts."""
    results = []
    results.append(_check_docker_installed())
    results.append(_check_docker_running())
    for port, service in REQUIRED_PORTS:
        results.append(_check_port(port, service))
    results.append(_check_disk_space(install_path))
    return results


def is_critical_failure(results: list) -> bool:
    """Return True if Docker is not installed or not running."""
    for r in results:
        if r["name"] in ("Docker installed", "Docker daemon running"):
            if r["status"] == "fail":
                return True
    return False
