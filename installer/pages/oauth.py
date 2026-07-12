"""OAuth credentials page."""
import tkinter as tk
from tkinter import ttk
import webbrowser
from .base import WizardPage

PROVIDERS = [
    {
        "name": "Google",
        "key_prefix": "google",
        "console_url": "https://console.developers.google.com/",
        "console_label": "Google Cloud Console",
    },
    {
        "name": "LinkedIn",
        "key_prefix": "linkedin",
        "console_url": "https://www.linkedin.com/developers/apps",
        "console_label": "LinkedIn Developers",
    },
    {
        "name": "Facebook",
        "key_prefix": "facebook",
        "console_url": "https://developers.facebook.com/apps/",
        "console_label": "Facebook for Developers",
    },
]


class OAuthPage(WizardPage):
    title = "OAuth Credentials"
    subtitle = "Configure social login providers (at least one required)"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=12)

        tk.Label(
            body,
            text="At least one OAuth provider is required for user authentication.\n"
                 "Get credentials from each provider's developer console.",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10), justify="left"
        ).pack(anchor="w", pady=(0, 10))

        self._vars = {}

        for provider in PROVIDERS:
            lf = tk.LabelFrame(
                body, text=f"  {provider['name']}  ",
                bg="#FFFFFF", fg="#0078D4",
                font=("Segoe UI", 10, "bold"),
                padx=10, pady=8
            )
            lf.pack(fill="x", pady=4)

            prefix = provider["key_prefix"]
            self._vars[prefix] = {}

            for label, key, is_pass in [
                ("Client ID", "client_id", False),
                ("Client Secret", "client_secret", True),
            ]:
                row = tk.Frame(lf, bg="#FFFFFF")
                row.pack(anchor="w", pady=2, fill="x")
                tk.Label(row, text=label + ":", bg="#FFFFFF", fg="#323130",
                         font=("Segoe UI", 10), width=14, anchor="w").pack(side="left")
                var = tk.StringVar()
                self._vars[prefix][key] = var
                ttk.Entry(row, textvariable=var, width=45,
                          show="*" if is_pass else "").pack(side="left")

            # Link to developer console
            link_row = tk.Frame(lf, bg="#FFFFFF")
            link_row.pack(anchor="w", pady=(4, 0))
            url = provider["console_url"]
            link_text = f"Open {provider['console_label']} ↗"
            link = tk.Label(
                link_row, text=link_text, bg="#FFFFFF", fg="#0078D4",
                font=("Segoe UI", 9, "underline"), cursor="hand2"
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

    def validate(self) -> tuple:
        for provider in PROVIDERS:
            prefix = provider["key_prefix"]
            cid = self._vars[prefix]["client_id"].get().strip()
            csec = self._vars[prefix]["client_secret"].get().strip()
            if cid and csec:
                return True, ""
        return False, "At least one OAuth provider must have both Client ID and Client Secret filled in."

    def get_values(self) -> dict:
        result = {}
        for provider in PROVIDERS:
            prefix = provider["key_prefix"]
            result[f"{prefix}_client_id"] = self._vars[prefix]["client_id"].get().strip()
            result[f"{prefix}_client_secret"] = self._vars[prefix]["client_secret"].get().strip()
        return result
