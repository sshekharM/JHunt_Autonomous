"""First admin account creation page."""
import re
import tkinter as tk
from tkinter import ttk
from .base import WizardPage

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminPage(WizardPage):
    title = "Admin Account"
    subtitle = "Create the first Super Admin account for jH_ANS"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(
            body,
            text="This account will have full administrative access to the jH_ANS dashboard. "
                 "You will be prompted to configure two-factor authentication on first login.",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10), wraplength=560, justify="left"
        ).pack(anchor="w", pady=(0, 16))

        self._vars = {}
        fields = [
            ("Full Name", "admin_name", False, ""),
            ("Email Address", "admin_email", False, ""),
            ("Password", "admin_password", True, ""),
            ("Confirm Password", "admin_confirm", True, ""),
        ]

        for label, key, is_pass, default in fields:
            row = tk.Frame(body, bg="#FFFFFF")
            row.pack(anchor="w", pady=5, fill="x")
            tk.Label(row, text=label + ":", bg="#FFFFFF", fg="#323130",
                     font=("Segoe UI", 10), width=18, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            self._vars[key] = var
            ttk.Entry(row, textvariable=var, width=38,
                      show="*" if is_pass else "").pack(side="left")

        # Password strength hint
        tk.Label(
            body,
            text="Password must be at least 12 characters and include uppercase, "
                 "lowercase, a number, and a special character.",
            bg="#FFFFFF", fg="#605E5C",
            font=("Segoe UI", 9), wraplength=560, justify="left"
        ).pack(anchor="w", pady=(4, 0))

        # 2FA note
        tk.Frame(body, bg="#E0EBF8", height=1).pack(fill="x", pady=12)
        totp_frame = tk.Frame(body, bg="#EFF6FC")
        totp_frame.pack(fill="x")
        tk.Label(
            totp_frame,
            text="Two-Factor Authentication (TOTP)",
            bg="#EFF6FC", fg="#0078D4",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(
            totp_frame,
            text="You will be prompted to scan a QR code with your authenticator app "
                 "(Google Authenticator, Authy, etc.) on your first login. "
                 "2FA is mandatory for admin accounts.",
            bg="#EFF6FC", fg="#323130",
            font=("Segoe UI", 9), wraplength=540, justify="left"
        ).pack(anchor="w", padx=10, pady=(0, 8))

    def _password_strong(self, pwd: str) -> bool:
        if len(pwd) < 12:
            return False
        if not re.search(r"[A-Z]", pwd):
            return False
        if not re.search(r"[a-z]", pwd):
            return False
        if not re.search(r"\d", pwd):
            return False
        if not re.search(r"[^A-Za-z0-9]", pwd):
            return False
        return True

    def validate(self) -> tuple:
        name = self._vars["admin_name"].get().strip()
        email = self._vars["admin_email"].get().strip()
        pwd = self._vars["admin_password"].get()
        confirm = self._vars["admin_confirm"].get()

        if not name:
            return False, "Full name is required."
        if not email or not EMAIL_RE.match(email):
            return False, "Please enter a valid email address."
        if not pwd:
            return False, "Password is required."
        if not self._password_strong(pwd):
            return False, (
                "Password must be at least 12 characters and include uppercase, "
                "lowercase, a number, and a special character."
            )
        if pwd != confirm:
            return False, "Passwords do not match."
        return True, ""

    def get_values(self) -> dict:
        return {
            "admin_name": self._vars["admin_name"].get().strip(),
            "admin_email": self._vars["admin_email"].get().strip(),
            "admin_password": self._vars["admin_password"].get(),
        }
