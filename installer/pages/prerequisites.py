"""Prerequisites check page."""
import sys
import tkinter as tk
from tkinter import ttk
import threading
import webbrowser
from .base import WizardPage
from ..core import prereq_checker

DOCKER_INSTALL_URL = "https://docs.docker.com/desktop/install/windows-install/"


class PrerequisitesPage(WizardPage):
    title = "Prerequisites"
    subtitle = "Checking system requirements before installation"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(
            body,
            text="Checking requirements...",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 8))

        # Container for check rows
        self._checks_frame = tk.Frame(body, bg="#FFFFFF")
        self._checks_frame.pack(fill="x")

        # Action area (shown if Docker missing)
        self._action_frame = tk.Frame(body, bg="#FFFFFF")
        self._action_frame.pack(fill="x", pady=(8, 0))

        self._status_label = tk.Label(
            body, text="", bg="#FFFFFF", fg="#D13438",
            font=("Segoe UI", 10), wraplength=560, justify="left"
        )
        self._status_label.pack(anchor="w", pady=(8, 0))

        self._results = []
        self._critical_fail = False

        # Run checks in background thread so UI stays responsive
        threading.Thread(target=self._run_checks, daemon=True).start()

    def _run_checks(self):
        results = prereq_checker.check_all()
        self._results = results
        self._critical_fail = prereq_checker.is_critical_failure(results)
        # Update UI on main thread
        self.after(0, self._populate_results)

    def _populate_results(self):
        # Clear old rows
        for w in self._checks_frame.winfo_children():
            w.destroy()
        for w in self._action_frame.winfo_children():
            w.destroy()

        for r in self._results:
            row = tk.Frame(self._checks_frame, bg="#FFFFFF")
            row.pack(anchor="w", pady=2, fill="x")

            status = r["status"]
            if status == "ok":
                icon, color = "✓", "#107C10"
            elif status == "warn":
                icon, color = "⚠", "#FF8C00"
            else:
                icon, color = "✗", "#D13438"

            tk.Label(row, text=icon, bg="#FFFFFF", fg=color,
                     font=("Segoe UI", 11, "bold"), width=2).pack(side="left")
            tk.Label(row, text=r["name"], bg="#FFFFFF", fg="#323130",
                     font=("Segoe UI", 10), width=28, anchor="w").pack(side="left")
            tk.Label(row, text=r["message"], bg="#FFFFFF", fg="#605E5C",
                     font=("Segoe UI", 9), anchor="w").pack(side="left")

        if self._critical_fail:
            self._status_label.config(
                text="Critical requirements not met. Please install and start Docker before continuing."
            )
            link = tk.Label(
                self._action_frame,
                text="Download Docker Desktop for Windows",
                bg="#FFFFFF", fg="#0078D4",
                font=("Segoe UI", 10, "underline"),
                cursor="hand2"
            )
            link.pack(anchor="w")
            link.bind("<Button-1>", lambda e: webbrowser.open(DOCKER_INSTALL_URL))
            self.controller.set_next_enabled(False)
        else:
            self._status_label.config(text="")
            self.controller.set_next_enabled(True)

    def on_show(self):
        # Re-run checks each time page is shown (user may have installed Docker)
        for w in self._checks_frame.winfo_children():
            w.destroy()
        tk.Label(
            self._checks_frame,
            text="Running checks...",
            bg="#FFFFFF", fg="#605E5C",
            font=("Segoe UI", 10)
        ).pack(anchor="w")
        threading.Thread(target=self._run_checks, daemon=True).start()

    def validate(self) -> tuple:
        if self._critical_fail:
            return False, "Docker must be installed and running to continue."
        return True, ""

    def get_values(self) -> dict:
        return {}
