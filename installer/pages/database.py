"""Database configuration page."""
import tkinter as tk
from tkinter import ttk
from .base import WizardPage


class DatabasePage(WizardPage):
    title = "Database Settings"
    subtitle = "Configure PostgreSQL for jH_ANS"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(
            body,
            text="Choose how to provide the PostgreSQL database:",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(0, 12))

        self._db_mode = tk.StringVar(value="bundled")

        # Option 1 — Bundled
        bundled_frame = tk.Frame(body, bg="#FFFFFF")
        bundled_frame.pack(anchor="w", pady=2)
        tk.Radiobutton(
            bundled_frame, text="Use bundled PostgreSQL (recommended)",
            variable=self._db_mode, value="bundled",
            bg="#FFFFFF", fg="#323130", font=("Segoe UI", 10),
            command=self._on_mode_change, activebackground="#FFFFFF"
        ).pack(side="left")

        tk.Label(
            body,
            text="    Docker manages PostgreSQL automatically. No configuration needed.",
            bg="#FFFFFF", fg="#605E5C", font=("Segoe UI", 9)
        ).pack(anchor="w")

        # Option 2 — External
        external_frame = tk.Frame(body, bg="#FFFFFF")
        external_frame.pack(anchor="w", pady=(8, 2))
        tk.Radiobutton(
            external_frame, text="Use existing PostgreSQL server",
            variable=self._db_mode, value="external",
            bg="#FFFFFF", fg="#323130", font=("Segoe UI", 10),
            command=self._on_mode_change, activebackground="#FFFFFF"
        ).pack(side="left")

        # External fields container
        self._ext_frame = tk.Frame(body, bg="#F3F2F1", padx=12, pady=12)
        self._ext_frame.pack(fill="x", pady=(4, 0))

        fields = [
            ("Host", "db_host", "localhost", False),
            ("Port", "db_port", "5432", False),
            ("Database name", "db_name", "jhans", False),
            ("Username", "db_user", "jhans", False),
            ("Password", "db_password", "", True),
        ]
        self._ext_vars = {}
        for label, key, default, is_pass in fields:
            row = tk.Frame(self._ext_frame, bg="#F3F2F1")
            row.pack(anchor="w", pady=3, fill="x")
            tk.Label(row, text=label + ":", bg="#F3F2F1", fg="#323130",
                     font=("Segoe UI", 10), width=16, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            self._ext_vars[key] = var
            entry = ttk.Entry(row, textvariable=var, width=30,
                              show="*" if is_pass else "")
            entry.pack(side="left")

        # Test connection button
        btn_row = tk.Frame(self._ext_frame, bg="#F3F2F1")
        btn_row.pack(anchor="w", pady=(8, 0))
        self._test_btn = ttk.Button(
            btn_row, text="Test Connection", command=self._test_connection
        )
        self._test_btn.pack(side="left")
        self._test_result = tk.Label(
            btn_row, text="", bg="#F3F2F1", font=("Segoe UI", 9)
        )
        self._test_result.pack(side="left", padx=8)

        self._on_mode_change()  # Set initial state

    def _on_mode_change(self):
        mode = self._db_mode.get()
        state = "normal" if mode == "external" else "disabled"
        for child in self._ext_frame.winfo_children():
            for w in child.winfo_children():
                try:
                    w.config(state=state)
                except Exception:
                    pass

    def _test_connection(self):
        v = self._ext_vars
        host = v["db_host"].get().strip()
        port = v["db_port"].get().strip()
        name = v["db_name"].get().strip()
        user = v["db_user"].get().strip()
        pwd = v["db_password"].get()

        try:
            import psycopg2
            conn = psycopg2.connect(
                host=host, port=int(port), dbname=name,
                user=user, password=pwd, connect_timeout=5
            )
            conn.close()
            self._test_result.config(
                text="Connection successful!", fg="#107C10"
            )
        except ImportError:
            self._test_result.config(
                text="psycopg2 not installed — will validate at startup", fg="#FF8C00"
            )
        except Exception as e:
            self._test_result.config(
                text=f"Failed: {e}", fg="#D13438"
            )

    def validate(self) -> tuple:
        if self._db_mode.get() == "external":
            v = self._ext_vars
            if not v["db_host"].get().strip():
                return False, "Database host is required."
            if not v["db_name"].get().strip():
                return False, "Database name is required."
            if not v["db_user"].get().strip():
                return False, "Database username is required."
            port = v["db_port"].get().strip()
            try:
                p = int(port)
                if not (1 <= p <= 65535):
                    raise ValueError()
            except ValueError:
                return False, "Port must be a number between 1 and 65535."
        return True, ""

    def get_values(self) -> dict:
        mode = self._db_mode.get()
        if mode == "bundled":
            return {
                "db_mode": "bundled",
                "db_host": "db",
                "db_port": "5432",
                "db_name": "jhans",
                "db_user": "jhans",
                "db_password": "",
            }
        v = self._ext_vars
        return {
            "db_mode": "external",
            "db_host": v["db_host"].get().strip(),
            "db_port": v["db_port"].get().strip(),
            "db_name": v["db_name"].get().strip(),
            "db_user": v["db_user"].get().strip(),
            "db_password": v["db_password"].get(),
        }
