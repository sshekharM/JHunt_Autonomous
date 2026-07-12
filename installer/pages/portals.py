"""System portal account credentials page."""
import tkinter as tk
from tkinter import ttk
from .base import WizardPage

PORTALS = [
    ("Naukri", "naukri"),
    ("LinkedIn", "linkedin"),
    ("Glassdoor", "glassdoor"),
    ("Indeed", "indeed"),
    ("Monster", "monster"),
    ("Shine", "shine"),
]


class PortalsPage(WizardPage):
    title = "Portal Accounts"
    subtitle = "System-owned crawling accounts for job discovery"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=12)

        tk.Label(
            body,
            text="These are dedicated system accounts used only for job discovery crawling.\n"
                 "They are NOT used to apply on your behalf — keep them separate from your personal accounts.",
            bg="#FFFFFF", fg="#605E5C",
            font=("Segoe UI", 9, "italic"), wraplength=560, justify="left"
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(
            body,
            text="All portal credentials are optional. Unfilled portals will be skipped during crawling.",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10), wraplength=560, justify="left"
        ).pack(anchor="w", pady=(0, 8))

        # Tab control
        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        self._portal_vars = {}

        for display_name, key in PORTALS:
            tab = tk.Frame(notebook, bg="#FFFFFF", padx=16, pady=16)
            notebook.add(tab, text=display_name)

            self._portal_vars[key] = {}

            for label, field, is_pass in [
                ("Email / Username", "email", False),
                ("Password", "password", True),
            ]:
                row = tk.Frame(tab, bg="#FFFFFF")
                row.pack(anchor="w", pady=4, fill="x")
                tk.Label(row, text=label + ":", bg="#FFFFFF", fg="#323130",
                         font=("Segoe UI", 10), width=16, anchor="w").pack(side="left")
                var = tk.StringVar()
                self._portal_vars[key][field] = var
                ttk.Entry(row, textvariable=var, width=40,
                          show="*" if is_pass else "").pack(side="left")

            tk.Label(
                tab,
                text=f"Create a dedicated {display_name} account for crawling. "
                     f"Sharing personal credentials is not recommended.",
                bg="#FFFFFF", fg="#605E5C",
                font=("Segoe UI", 8), wraplength=440, justify="left"
            ).pack(anchor="w", pady=(10, 0))

    def validate(self) -> tuple:
        # All portals are optional — no validation required
        return True, ""

    def get_values(self) -> dict:
        result = {}
        for _, key in PORTALS:
            result[f"{key}_system_email"] = self._portal_vars[key]["email"].get().strip()
            result[f"{key}_system_password"] = self._portal_vars[key]["password"].get()
        return result
