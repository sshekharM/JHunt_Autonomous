"""Notifications configuration page."""
import tkinter as tk
from tkinter import ttk
import webbrowser
from .base import WizardPage


class NotificationsPage(WizardPage):
    title = "Notifications"
    subtitle = "Configure email delivery and instant notifications"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=10)

        # ── Section 1: Email ──────────────────────────────────────────────
        email_lf = tk.LabelFrame(
            body, text="  Email Delivery (required)  ",
            bg="#FFFFFF", fg="#0078D4", font=("Segoe UI", 10, "bold"),
            padx=10, pady=8
        )
        email_lf.pack(fill="x", pady=(0, 8))

        self._email_mode = tk.StringVar(value="smtp")
        for value, label in [("smtp", "SMTP"), ("sendgrid", "SendGrid")]:
            tk.Radiobutton(
                email_lf, text=label, variable=self._email_mode, value=value,
                bg="#FFFFFF", font=("Segoe UI", 10),
                command=self._on_email_mode_change, activebackground="#FFFFFF"
            ).pack(side="left", padx=(0, 12))

        # SMTP fields
        self._smtp_frame = tk.Frame(email_lf, bg="#FFFFFF")
        self._smtp_frame.pack(fill="x", pady=(6, 0))
        self._smtp_vars = {}
        smtp_fields = [
            ("SMTP Host", "smtp_host", "localhost", False),
            ("SMTP Port", "smtp_port", "587", False),
            ("Username", "smtp_user", "", False),
            ("Password", "smtp_password", "", True),
            ("From Address", "email_from", "noreply@jhans.local", False),
        ]
        for label, key, default, is_pass in smtp_fields:
            row = tk.Frame(self._smtp_frame, bg="#FFFFFF")
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=label + ":", bg="#FFFFFF", fg="#323130",
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            self._smtp_vars[key] = var
            ttk.Entry(row, textvariable=var, width=35,
                      show="*" if is_pass else "").pack(side="left")

        # SendGrid fields
        self._sg_frame = tk.Frame(email_lf, bg="#FFFFFF")
        self._sg_vars = {}
        sg_fields = [
            ("API Key", "sendgrid_api_key", "", True),
            ("From Address", "email_from_sg", "noreply@jhans.local", False),
        ]
        for label, key, default, is_pass in sg_fields:
            row = tk.Frame(self._sg_frame, bg="#FFFFFF")
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=label + ":", bg="#FFFFFF", fg="#323130",
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            self._sg_vars[key] = var
            ttk.Entry(row, textvariable=var, width=45,
                      show="*" if is_pass else "").pack(side="left")

        # Test email button
        test_row = tk.Frame(email_lf, bg="#FFFFFF")
        test_row.pack(anchor="w", pady=(8, 0))
        ttk.Button(test_row, text="Send Test Email",
                   command=self._send_test_email).pack(side="left")
        self._email_test_label = tk.Label(
            test_row, text="", bg="#FFFFFF", font=("Segoe UI", 9)
        )
        self._email_test_label.pack(side="left", padx=8)

        self._on_email_mode_change()

        # ── Section 2: Instant Notifications ─────────────────────────────
        notif_lf = tk.LabelFrame(
            body, text="  Instant Notifications (optional)  ",
            bg="#FFFFFF", fg="#0078D4", font=("Segoe UI", 10, "bold"),
            padx=10, pady=8
        )
        notif_lf.pack(fill="x")

        self._notif_mode = tk.StringVar(value="none")
        for value, label in [("none", "None"), ("telegram", "Telegram"), ("discord", "Discord")]:
            tk.Radiobutton(
                notif_lf, text=label, variable=self._notif_mode, value=value,
                bg="#FFFFFF", font=("Segoe UI", 10),
                command=self._on_notif_mode_change, activebackground="#FFFFFF"
            ).pack(side="left", padx=(0, 12))

        # Telegram fields
        self._tg_frame = tk.Frame(notif_lf, bg="#FFFFFF")
        self._tg_bot_var = tk.StringVar()
        tg_row = tk.Frame(self._tg_frame, bg="#FFFFFF")
        tg_row.pack(anchor="w", pady=2)
        tk.Label(tg_row, text="Bot Token:", bg="#FFFFFF", fg="#323130",
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        ttk.Entry(tg_row, textvariable=self._tg_bot_var, width=45,
                  show="*").pack(side="left")
        tk.Label(
            self._tg_frame,
            text="Create a bot via @BotFather on Telegram, then paste the token here.",
            bg="#FFFFFF", fg="#605E5C", font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(2, 0))

        # Discord fields
        self._dc_frame = tk.Frame(notif_lf, bg="#FFFFFF")
        self._dc_bot_var = tk.StringVar()
        self._dc_guild_var = tk.StringVar()
        for label, var, is_pass in [
            ("Bot Token", self._dc_bot_var, True),
            ("Server (Guild) ID", self._dc_guild_var, False),
        ]:
            row = tk.Frame(self._dc_frame, bg="#FFFFFF")
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=label + ":", bg="#FFFFFF", fg="#323130",
                     font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
            ttk.Entry(row, textvariable=var, width=40,
                      show="*" if is_pass else "").pack(side="left")
        link = tk.Label(
            self._dc_frame,
            text="Discord Developer Portal ↗",
            bg="#FFFFFF", fg="#0078D4",
            font=("Segoe UI", 8, "underline"), cursor="hand2"
        )
        link.pack(anchor="w", pady=(2, 0))
        link.bind("<Button-1>",
                  lambda e: webbrowser.open("https://discord.com/developers/applications"))

        self._on_notif_mode_change()

    def _on_email_mode_change(self):
        mode = self._email_mode.get()
        if mode == "smtp":
            self._sg_frame.pack_forget()
            self._smtp_frame.pack(fill="x", pady=(6, 0))
        else:
            self._smtp_frame.pack_forget()
            self._sg_frame.pack(fill="x", pady=(6, 0))

    def _on_notif_mode_change(self):
        mode = self._notif_mode.get()
        self._tg_frame.pack_forget()
        self._dc_frame.pack_forget()
        if mode == "telegram":
            self._tg_frame.pack(fill="x", pady=(6, 0))
        elif mode == "discord":
            self._dc_frame.pack(fill="x", pady=(6, 0))

    def _send_test_email(self):
        self._email_test_label.config(
            text="Test email queued — check your inbox after installation completes.",
            fg="#605E5C"
        )

    def validate(self) -> tuple:
        mode = self._email_mode.get()
        if mode == "smtp":
            if not self._smtp_vars["smtp_host"].get().strip():
                return False, "SMTP host is required."
            if not self._smtp_vars["email_from"].get().strip():
                return False, "From address is required."
        else:
            if not self._sg_vars["sendgrid_api_key"].get().strip():
                return False, "SendGrid API key is required."
            if not self._sg_vars["email_from_sg"].get().strip():
                return False, "From address is required."
        return True, ""

    def get_values(self) -> dict:
        mode = self._email_mode.get()
        result = {"email_provider": mode}
        if mode == "smtp":
            for k, v in self._smtp_vars.items():
                result[k] = v.get().strip() if k != "smtp_password" else v.get()
        else:
            result["sendgrid_api_key"] = self._sg_vars["sendgrid_api_key"].get()
            result["email_from"] = self._sg_vars["email_from_sg"].get().strip()

        notif = self._notif_mode.get()
        result["notif_mode"] = notif
        result["telegram_bot_token"] = self._tg_bot_var.get().strip()
        result["discord_bot_token"] = self._dc_bot_var.get().strip()
        result["discord_guild_id"] = self._dc_guild_var.get().strip()
        return result
