import tkinter as tk
from tkinter import ttk
from abc import ABC, abstractmethod


class WizardPage(tk.Frame, ABC):
    """Base class for all wizard pages."""
    title: str = ""
    subtitle: str = ""

    def __init__(self, parent, controller):
        super().__init__(parent, bg="#FFFFFF")
        self.controller = controller
        self._build_header()
        self._build_body()

    def _build_header(self):
        """Blue header bar (like AADConnect) with title + subtitle."""
        header = tk.Frame(self, bg="#0078D4", height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        inner = tk.Frame(header, bg="#0078D4")
        inner.pack(side="left", fill="both", expand=True, padx=20, pady=10)

        tk.Label(
            inner, text=self.title, bg="#0078D4", fg="white",
            font=("Segoe UI", 14, "bold"), anchor="w"
        ).pack(anchor="w")

        if self.subtitle:
            tk.Label(
                inner, text=self.subtitle, bg="#0078D4", fg="#CCDDFF",
                font=("Segoe UI", 9), anchor="w"
            ).pack(anchor="w")

    @abstractmethod
    def _build_body(self): ...

    def validate(self) -> tuple:
        """Return (is_valid, error_message). Override in pages that have inputs."""
        return True, ""

    def get_values(self) -> dict:
        """Return this page's collected values. Override as needed."""
        return {}

    def on_show(self):
        """Called each time the page becomes visible. Override to refresh data."""
        pass
