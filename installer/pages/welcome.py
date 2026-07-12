import tkinter as tk
from tkinter import ttk
from .base import WizardPage

LOGO_TEXT = r"""
    _ _   _       _    _   _ ____
   (_) | | |     / \  | \ | / ___|
   | | |_| |    / _ \ |  \| \___ \
   | |  _  |   / ___ \| |\  |___) |
  _/ |_| |_|  /_/   \_\_| \_|____/
 |__/  Autonomous Job Hunt System
"""

LICENSE_TEXT = """\
MIT License — Copyright (c) 2025 jH_ANS Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


class WelcomePage(WizardPage):
    title = "Welcome to jH_ANS Setup"
    subtitle = "Autonomous Job Hunt System — Installation Wizard"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # Logo / branding
        logo_label = tk.Label(
            body, text=LOGO_TEXT, bg="#FFFFFF", fg="#0078D4",
            font=("Courier New", 9, "bold"), justify="left", anchor="w"
        )
        logo_label.pack(anchor="w")

        # Description
        desc = (
            "This wizard will guide you through the installation of jH_ANS — "
            "a fully automated, AI-powered job hunt platform that monitors portals, "
            "applies to matching roles, and keeps you informed at every step.\n\n"
            "The wizard will collect your configuration, set up Docker services, "
            "and prepare jH_ANS for first use. The process takes approximately "
            "5-10 minutes depending on your internet speed."
        )
        tk.Label(
            body, text=desc, bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10), justify="left", wraplength=560, anchor="w"
        ).pack(anchor="w", pady=(4, 12))

        # Separator
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8)

        # License summary
        tk.Label(
            body, text="License Summary", bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 4))

        bullets = [
            "Free to use, copy, modify, and distribute (MIT License)",
            "No warranty is provided — use at your own risk",
            "Third-party services (Anthropic, SendGrid, etc.) have their own terms",
        ]
        for b in bullets:
            row = tk.Frame(body, bg="#FFFFFF")
            row.pack(anchor="w", pady=1)
            tk.Label(row, text="•", bg="#FFFFFF", fg="#0078D4",
                     font=("Segoe UI", 10)).pack(side="left")
            tk.Label(row, text=b, bg="#FFFFFF", fg="#323130",
                     font=("Segoe UI", 10), wraplength=530, justify="left").pack(side="left", padx=6)

        # License scroll area
        frame = tk.Frame(body, bg="#F3F2F1", bd=1, relief="sunken")
        frame.pack(fill="x", pady=(8, 4))
        scroll = tk.Scrollbar(frame)
        scroll.pack(side="right", fill="y")
        text = tk.Text(
            frame, height=5, wrap="word", font=("Segoe UI", 8),
            bg="#F3F2F1", fg="#605E5C", relief="flat",
            yscrollcommand=scroll.set
        )
        text.insert("1.0", LICENSE_TEXT)
        text.config(state="disabled")
        text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scroll.config(command=text.yview)

        # Accept checkbox
        self._accepted = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(
            body,
            text="I have read and accept the license terms",
            variable=self._accepted,
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10),
            activebackground="#FFFFFF",
            command=self._on_accept_toggle
        )
        cb.pack(anchor="w", pady=(6, 0))

    def _on_accept_toggle(self):
        accepted = self._accepted.get()
        self.controller.set_next_enabled(accepted)

    def on_show(self):
        self.controller.set_next_enabled(self._accepted.get())

    def validate(self) -> tuple:
        if not self._accepted.get():
            return False, "You must accept the license terms to continue."
        return True, ""

    def get_values(self) -> dict:
        return {}
