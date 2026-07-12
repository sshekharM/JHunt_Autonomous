"""Installation directory selection page."""
import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, filedialog
from .base import WizardPage


def _default_install_path() -> str:
    if sys.platform == "win32":
        return r"C:\jH_ANS"
    elif sys.platform == "darwin":
        return "/opt/jhans"
    else:
        return "/opt/jhans"


class InstallDirPage(WizardPage):
    title = "Installation Directory"
    subtitle = "Choose where jH_ANS will be installed"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(
            body,
            text="Select the folder where jH_ANS will store its configuration, "
                 "Docker Compose files, and persistent data volumes.",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10), wraplength=560, justify="left"
        ).pack(anchor="w", pady=(0, 16))

        # Path entry + browse
        path_frame = tk.Frame(body, bg="#FFFFFF")
        path_frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            path_frame, text="Install to:", bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10)
        ).pack(side="left")

        self._path_var = tk.StringVar(value=_default_install_path())
        self._path_entry = ttk.Entry(path_frame, textvariable=self._path_var, width=45)
        self._path_entry.pack(side="left", padx=8)

        ttk.Button(
            path_frame, text="Browse...", command=self._browse
        ).pack(side="left")

        # Disk usage estimate
        tk.Label(
            body,
            text="Estimated disk usage: ~8 GB (Docker images + persistent data volumes)",
            bg="#FFFFFF", fg="#605E5C",
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(4, 0))

        # Space available label (dynamic)
        self._space_label = tk.Label(
            body, text="", bg="#FFFFFF", fg="#605E5C", font=("Segoe UI", 9)
        )
        self._space_label.pack(anchor="w")

        # Warning label
        self._warn_label = tk.Label(
            body, text="", bg="#FFFFFF", fg="#D13438",
            font=("Segoe UI", 9), wraplength=560, justify="left"
        )
        self._warn_label.pack(anchor="w", pady=(4, 0))

        # Update space info when path changes
        self._path_var.trace_add("write", self._update_space_info)
        self._update_space_info()

    def _browse(self):
        chosen = filedialog.askdirectory(
            title="Select Installation Directory",
            initialdir=self._path_var.get() if os.path.exists(self._path_var.get()) else "/"
        )
        if chosen:
            self._path_var.set(chosen)

    def _update_space_info(self, *_):
        path = self._path_var.get().strip()
        # Walk up until we find an existing parent
        check_path = path
        while check_path and not os.path.exists(check_path):
            parent = os.path.dirname(check_path)
            if parent == check_path:
                break
            check_path = parent

        if check_path and os.path.exists(check_path):
            try:
                usage = shutil.disk_usage(check_path)
                free_gb = usage.free / (1024 ** 3)
                self._space_label.config(
                    text=f"Free space on selected drive: {free_gb:.1f} GB"
                )
            except Exception:
                self._space_label.config(text="")
        else:
            self._space_label.config(text="")

    def validate(self) -> tuple:
        path = self._path_var.get().strip()
        if not path:
            return False, "Please specify an installation directory."

        # Check that we can write to the parent directory
        parent = path if os.path.exists(path) else os.path.dirname(path)
        while parent and not os.path.exists(parent):
            parent = os.path.dirname(parent)

        if not parent or not os.path.exists(parent):
            return False, f"Cannot find a writable parent directory for: {path}"

        if not os.access(parent, os.W_OK):
            return False, f"Cannot write to {parent}. Run the installer as Administrator."

        return True, ""

    def get_values(self) -> dict:
        return {"install_dir": self._path_var.get().strip()}
