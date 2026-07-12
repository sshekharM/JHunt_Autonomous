"""Final install page: summary → progress → completion."""
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext
from .base import WizardPage
from ..core import env_writer, docker_runner, autostart

DASHBOARD_URL = "http://localhost:8000"

# Keys that should be masked in the summary
SECRET_KEYS = {
    "db_password", "admin_password", "admin_confirm",
    "anthropic_api_key", "smtp_password", "sendgrid_api_key",
    "telegram_bot_token", "discord_bot_token",
    "google_client_secret", "linkedin_client_secret", "facebook_client_secret",
    "naukri_system_password", "linkedin_system_password", "glassdoor_system_password",
    "indeed_system_password", "monster_system_password", "shine_system_password",
}

SUMMARY_LABELS = {
    "install_dir": "Install Directory",
    "db_mode": "Database Mode",
    "db_host": "DB Host",
    "db_name": "DB Name",
    "db_user": "DB User",
    "llm_choice": "LLM Provider",
    "ollama_model": "Ollama Model",
    "email_provider": "Email Provider",
    "smtp_host": "SMTP Host",
    "notif_mode": "Notifications",
    "admin_name": "Admin Name",
    "admin_email": "Admin Email",
    "google_client_id": "Google Client ID",
    "linkedin_client_id": "LinkedIn Client ID",
    "facebook_client_id": "Facebook Client ID",
}


class InstallPage(WizardPage):
    title = "Install"
    subtitle = "Review settings and begin installation"

    def _build_body(self):
        self._state = "summary"  # or "installing"

        # ── Summary view ────────────────────────────────────────────────
        self._summary_frame = tk.Frame(self, bg="#FFFFFF")
        self._summary_frame.pack(fill="both", expand=True, padx=24, pady=12)

        tk.Label(
            self._summary_frame,
            text="Review your configuration before installing. "
                 "Click Install to begin.",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(0, 8))

        # Scrollable summary table
        table_outer = tk.Frame(self._summary_frame, bg="#F3F2F1", bd=1, relief="sunken")
        table_outer.pack(fill="both", expand=True)

        self._summary_scroll = tk.Scrollbar(table_outer)
        self._summary_scroll.pack(side="right", fill="y")
        self._summary_text = tk.Text(
            table_outer, height=14, wrap="none",
            font=("Courier New", 9),
            bg="#F3F2F1", fg="#323130", relief="flat",
            yscrollcommand=self._summary_scroll.set
        )
        self._summary_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self._summary_scroll.config(command=self._summary_text.yview)

        # Install button (replaces Next in this page)
        self._install_btn = ttk.Button(
            self._summary_frame, text="Install",
            command=self._start_install
        )
        self._install_btn.pack(anchor="e", pady=(8, 0))

        # ── Installing view ─────────────────────────────────────────────
        self._install_frame = tk.Frame(self, bg="#FFFFFF")

        status_bar = tk.Frame(self._install_frame, bg="#FFFFFF")
        status_bar.pack(fill="x", padx=24, pady=(12, 4))
        self._status_label = tk.Label(
            status_bar, text="Preparing...",
            bg="#FFFFFF", fg="#0078D4",
            font=("Segoe UI", 10, "bold"), anchor="w"
        )
        self._status_label.pack(anchor="w")

        self._progress = ttk.Progressbar(
            self._install_frame, mode="indeterminate", length=600
        )
        self._progress.pack(fill="x", padx=24, pady=(0, 8))
        self._progress.start(10)

        log_outer = tk.Frame(self._install_frame, bg="#1E1E1E", bd=1, relief="sunken")
        log_outer.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        self._log_scroll = tk.Scrollbar(log_outer)
        self._log_scroll.pack(side="right", fill="y")
        self._log_text = tk.Text(
            log_outer, wrap="word",
            font=("Courier New", 8),
            bg="#1E1E1E", fg="#D4D4D4", insertbackground="#D4D4D4",
            relief="flat", state="disabled",
            yscrollcommand=self._log_scroll.set
        )
        self._log_text.pack(side="left", fill="both", expand=True)
        self._log_scroll.config(command=self._log_text.yview)

        self._finish_frame = tk.Frame(self._install_frame, bg="#FFFFFF")
        self._finish_frame.pack(fill="x", padx=24, pady=(0, 8))

    def on_show(self):
        """Populate summary when page becomes visible."""
        config = self.controller.collect_config()
        self._populate_summary(config)
        # Hide Back/Next, show Install button
        self.controller.set_nav_visible(back=True, next_=False, cancel=True)

    def _populate_summary(self, config: dict):
        self._summary_text.config(state="normal")
        self._summary_text.delete("1.0", "end")

        lines = []
        for key, label in SUMMARY_LABELS.items():
            val = config.get(key, "")
            if not val:
                continue
            if key in SECRET_KEYS:
                display = "*" * min(len(str(val)), 8) if val else "(not set)"
            else:
                display = str(val)
            lines.append(f"  {label:<28} {display}")

        # Show any extra keys not in the label map that are non-empty / non-secret
        for key, val in sorted(config.items()):
            if key in SUMMARY_LABELS or key in SECRET_KEYS:
                continue
            if not val:
                continue
            label = key.replace("_", " ").title()
            lines.append(f"  {label:<28} {val}")

        self._summary_text.insert("1.0", "\n".join(lines))
        self._summary_text.config(state="disabled")

    def _start_install(self):
        """Switch to installing view and kick off background install thread."""
        self._summary_frame.pack_forget()
        self._install_frame.pack(fill="both", expand=True)
        self.controller.set_nav_visible(back=False, next_=False, cancel=False)
        self._install_btn.config(state="disabled")

        config = self.controller.collect_config()
        install_dir = config.get("install_dir", "/opt/jhans")
        self._config = config
        self._install_dir = install_dir

        threading.Thread(
            target=self._do_install,
            args=(config, install_dir),
            daemon=True
        ).start()

    def _log(self, line: str):
        """Append a line to the log text widget (thread-safe via after)."""
        def _append():
            self._log_text.config(state="normal")
            self._log_text.insert("end", line + "\n")
            self._log_text.see("end")
            self._log_text.config(state="disabled")
        self.after(0, _append)

    def _set_progress(self, pct: int, message: str):
        def _update():
            if self._progress["mode"] == "indeterminate":
                self._progress.stop()
                self._progress.config(mode="determinate", maximum=100)
            self._progress["value"] = pct
            self._status_label.config(text=message)
        self.after(0, _update)

    def _do_install(self, config: dict, install_dir: str):
        success = False
        try:
            # Write .env
            self._log("Writing .env file...")
            env_path = env_writer.write_env(config, install_dir)
            self._log(f"Wrote: {env_path}")

            # Run docker install
            success = docker_runner.run_install(
                install_dir,
                progress_callback=self._set_progress,
                log_callback=self._log,
            )

            if success:
                # Register autostart
                self._log("\nRegistering auto-start...")
                ok = autostart.register_autostart(install_dir)
                if ok:
                    self._log("Auto-start registered successfully.")
                else:
                    self._log("WARNING: Could not register auto-start (non-fatal).")

        except Exception as e:
            self._log(f"\nFATAL ERROR: {e}")
            success = False

        self.after(0, lambda: self._on_install_done(success))

    def _on_install_done(self, success: bool):
        # Clear old finish widgets
        for w in self._finish_frame.winfo_children():
            w.destroy()

        if success:
            self._status_label.config(
                text="Installation complete!", fg="#107C10"
            )
            self._set_progress(100, "Installation complete!")

            tk.Label(
                self._finish_frame,
                text="jH_ANS is running. Open the dashboard to get started.",
                bg="#FFFFFF", fg="#107C10",
                font=("Segoe UI", 10, "bold")
            ).pack(side="left")

            ttk.Button(
                self._finish_frame,
                text="Open jH_ANS Dashboard",
                command=lambda: webbrowser.open(DASHBOARD_URL)
            ).pack(side="right")
        else:
            self._status_label.config(
                text="Installation failed. See log above for details.", fg="#D13438"
            )
            self._set_progress(0, "Installation failed")

            retry_btn = ttk.Button(
                self._finish_frame, text="Retry",
                command=self._retry
            )
            retry_btn.pack(side="right")

            view_logs_btn = ttk.Button(
                self._finish_frame, text="View Full Log",
                command=self._view_logs
            )
            view_logs_btn.pack(side="right", padx=(0, 8))

    def _retry(self):
        # Clear log and restart
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")
        self._progress.config(mode="indeterminate")
        self._progress.start(10)
        self._status_label.config(text="Retrying...", fg="#0078D4")
        for w in self._finish_frame.winfo_children():
            w.destroy()
        threading.Thread(
            target=self._do_install,
            args=(self._config, self._install_dir),
            daemon=True
        ).start()

    def _view_logs(self):
        log_path = None
        try:
            import tempfile
            log_path = tempfile.mktemp(suffix=".txt", prefix="jhans_install_")
            with open(log_path, "w") as f:
                f.write(self._log_text.get("1.0", "end"))
            import subprocess
            if sys.platform == "win32":
                subprocess.Popen(["notepad", log_path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", log_path])
            else:
                subprocess.Popen(["xdg-open", log_path])
        except Exception as e:
            tk.messagebox.showerror("Error", f"Could not open log: {e}")

    def validate(self) -> tuple:
        return True, ""

    def get_values(self) -> dict:
        return {}
