"""Register jH_ANS as an auto-start service on Windows, Linux, and macOS."""
import os
import sys
import subprocess
import textwrap


def _register_windows(install_dir: str) -> bool:
    """Create a Windows Task Scheduler task that runs docker compose up on system start."""
    task_name = "jH_ANS_AutoStart"
    compose_files = [os.path.join(install_dir, "docker-compose.yml")]
    if os.path.exists(os.path.join(install_dir, "docker-compose.windows.yml")):
        compose_files.append(os.path.join(install_dir, "docker-compose.windows.yml"))

    # Build the action command
    file_args = " ".join(f'-f "{f}"' for f in compose_files if os.path.exists(f))
    action_cmd = f'docker compose {file_args} up -d'

    # Use schtasks to create the task
    cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'cmd /c "cd /d {install_dir} && {action_cmd}"',
        "/sc", "ONSTART",
        "/ru", "SYSTEM",
        "/rl", "HIGHEST",
        "/f",  # Force overwrite if exists
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def _register_linux(install_dir: str) -> bool:
    """Write a systemd unit and enable it."""
    unit_content = textwrap.dedent(f"""\
        [Unit]
        Description=jH_ANS Autonomous Job Hunt System
        Requires=docker.service
        After=docker.service network-online.target
        Wants=network-online.target

        [Service]
        Type=oneshot
        RemainAfterExit=yes
        WorkingDirectory={install_dir}
        ExecStart=/usr/bin/docker compose -f {install_dir}/docker-compose.yml up -d
        ExecStop=/usr/bin/docker compose -f {install_dir}/docker-compose.yml down
        TimeoutStartSec=300

        [Install]
        WantedBy=multi-user.target
    """)

    unit_path = "/etc/systemd/system/jhans.service"
    try:
        with open(unit_path, "w") as f:
            f.write(unit_content)
        subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=10)
        subprocess.run(["systemctl", "enable", "jhans.service"], check=True, timeout=10)
        return True
    except PermissionError:
        # Try with sudo
        try:
            subprocess.run(
                ["sudo", "tee", unit_path],
                input=unit_content.encode(), check=True, timeout=10
            )
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True, timeout=10)
            subprocess.run(["sudo", "systemctl", "enable", "jhans.service"],
                           check=True, timeout=10)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _register_macos(install_dir: str) -> bool:
    """Write a launchd plist and load it."""
    plist_content = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>com.jhans.autostart</string>
            <key>ProgramArguments</key>
            <array>
                <string>/usr/local/bin/docker</string>
                <string>compose</string>
                <string>-f</string>
                <string>{install_dir}/docker-compose.yml</string>
                <string>up</string>
                <string>-d</string>
            </array>
            <key>WorkingDirectory</key>
            <string>{install_dir}</string>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <false/>
            <key>StandardOutPath</key>
            <string>/var/log/jhans.log</string>
            <key>StandardErrorPath</key>
            <string>/var/log/jhans.err</string>
        </dict>
        </plist>
    """)

    plist_path = "/Library/LaunchDaemons/com.jhans.autostart.plist"
    try:
        with open(plist_path, "w") as f:
            f.write(plist_content)
        subprocess.run(["launchctl", "load", plist_path], check=True, timeout=10)
        return True
    except PermissionError:
        try:
            subprocess.run(
                ["sudo", "tee", plist_path],
                input=plist_content.encode(), check=True, timeout=10
            )
            subprocess.run(["sudo", "launchctl", "load", plist_path],
                           check=True, timeout=10)
            return True
        except Exception:
            return False
    except Exception:
        return False


def register_autostart(install_dir: str) -> bool:
    """
    Register jH_ANS to start automatically on system boot.
    Returns True on success, False on failure (non-fatal — installation continues).
    """
    if sys.platform == "win32":
        return _register_windows(install_dir)
    elif sys.platform == "darwin":
        return _register_macos(install_dir)
    else:
        return _register_linux(install_dir)
