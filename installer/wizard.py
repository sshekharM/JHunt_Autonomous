"""
jH_ANS Setup Wizard — main entry point.
Run with:  python wizard.py
"""
import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox

# Ensure the installer package is importable when run directly
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from installer.pages.welcome import WelcomePage
from installer.pages.prerequisites import PrerequisitesPage
from installer.pages.install_dir import InstallDirPage
from installer.pages.database import DatabasePage
from installer.pages.oauth import OAuthPage
from installer.pages.llm import LLMPage
from installer.pages.notifications import NotificationsPage
from installer.pages.portals import PortalsPage
from installer.pages.admin import AdminPage
from installer.pages.install import InstallPage

STEPS = [
    ("Welcome", WelcomePage),
    ("Prerequisites", PrerequisitesPage),
    ("Install Directory", InstallDirPage),
    ("Database", DatabasePage),
    ("OAuth Credentials", OAuthPage),
    ("LLM Settings", LLMPage),
    ("Notifications", NotificationsPage),
    ("Portal Accounts", PortalsPage),
    ("Admin Account", AdminPage),
    ("Install", InstallPage),
]

# Colours
C_BLUE = "#0078D4"
C_BLUE_DARK = "#005A9E"
C_SIDEBAR_BG = "#F3F2F1"
C_SIDEBAR_ACTIVE_BG = "#0078D4"
C_SIDEBAR_ACTIVE_FG = "#FFFFFF"
C_SIDEBAR_DONE_FG = "#107C10"
C_SIDEBAR_FUTURE_FG = "#A19F9D"
C_SIDEBAR_FG = "#323130"
C_WHITE = "#FFFFFF"
C_ERROR = "#D13438"
C_NAV_BG = "#F3F2F1"


class WizardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("jH_ANS Setup")
        self.resizable(False, False)
        self._center_window(700, 540)

        # Try to set icon
        try:
            icon_path = os.path.join(_HERE, "assets", "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self._current_index = 0
        self._pages = []

        self._build_ui()
        self._show_page(0)

    def _center_window(self, w: int, h: int):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # ── Main horizontal split ──────────────────────────────────────
        main = tk.Frame(self, bg=C_WHITE)
        main.pack(fill="both", expand=True)

        # Left sidebar
        self._sidebar = tk.Frame(main, bg=C_SIDEBAR_BG, width=160)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # jH_ANS brand at top of sidebar
        brand = tk.Frame(self._sidebar, bg=C_BLUE, height=44)
        brand.pack(fill="x")
        brand.pack_propagate(False)
        tk.Label(
            brand, text="jH_ANS", bg=C_BLUE, fg=C_WHITE,
            font=("Segoe UI", 12, "bold"), anchor="center"
        ).pack(fill="both", expand=True)

        # Step labels container
        self._step_labels = []
        for i, (name, _) in enumerate(STEPS):
            lbl = tk.Label(
                self._sidebar, text=f"  {i + 1}. {name}",
                bg=C_SIDEBAR_BG, fg=C_SIDEBAR_FUTURE_FG,
                font=("Segoe UI", 9), anchor="w", cursor="arrow",
                pady=6, padx=4
            )
            lbl.pack(fill="x")
            self._step_labels.append(lbl)

        # Right content area
        right = tk.Frame(main, bg=C_WHITE)
        right.pack(side="left", fill="both", expand=True)

        # Page container
        self._page_container = tk.Frame(right, bg=C_WHITE)
        self._page_container.pack(fill="both", expand=True)

        # ── Bottom nav bar ─────────────────────────────────────────────
        nav_sep = tk.Frame(right, bg="#D1D1D1", height=1)
        nav_sep.pack(fill="x")

        nav = tk.Frame(right, bg=C_NAV_BG, height=44)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        # Error label (left-aligned in nav bar)
        self._error_label = tk.Label(
            nav, text="", bg=C_NAV_BG, fg=C_ERROR,
            font=("Segoe UI", 9), anchor="w", wraplength=360
        )
        self._error_label.pack(side="left", padx=12)

        # Buttons right-aligned
        self._cancel_btn = ttk.Button(nav, text="Cancel", command=self._cancel)
        self._cancel_btn.pack(side="right", padx=(0, 12), pady=8)

        self._next_btn = ttk.Button(nav, text="Next >", command=self._next_page)
        self._next_btn.pack(side="right", padx=(0, 4), pady=8)

        self._back_btn = ttk.Button(nav, text="< Back", command=self._prev_page)
        self._back_btn.pack(side="right", padx=(0, 4), pady=8)

        # Instantiate all pages (hidden until needed)
        for _, PageClass in STEPS:
            page = PageClass(self._page_container, self)
            page.place(x=0, y=0, relwidth=1, relheight=1)
            self._pages.append(page)

    def _show_page(self, index: int):
        self._current_index = index
        page = self._pages[index]
        page.lift()
        page.on_show()
        self._update_sidebar()
        self._update_nav_buttons()
        self._error_label.config(text="")

    def _update_sidebar(self):
        idx = self._current_index
        for i, lbl in enumerate(self._step_labels):
            if i < idx:
                lbl.config(bg=C_SIDEBAR_BG, fg=C_SIDEBAR_DONE_FG,
                           text=f"  ✓ {i + 1}. {STEPS[i][0]}")
            elif i == idx:
                lbl.config(bg=C_SIDEBAR_ACTIVE_BG, fg=C_SIDEBAR_ACTIVE_FG,
                           text=f"  ▶ {i + 1}. {STEPS[i][0]}")
            else:
                lbl.config(bg=C_SIDEBAR_BG, fg=C_SIDEBAR_FUTURE_FG,
                           text=f"  {i + 1}. {STEPS[i][0]}")

    def _update_nav_buttons(self):
        idx = self._current_index
        self._back_btn.config(state="normal" if idx > 0 else "disabled")
        is_last = idx == len(STEPS) - 1
        if is_last:
            self._next_btn.config(state="disabled")
        else:
            self._next_btn.config(state="normal")

    def _next_page(self):
        page = self._pages[self._current_index]
        valid, msg = page.validate()
        if not valid:
            self._error_label.config(text=msg)
            return
        self._error_label.config(text="")
        next_idx = self._current_index + 1
        if next_idx < len(STEPS):
            self._show_page(next_idx)

    def _prev_page(self):
        prev_idx = self._current_index - 1
        if prev_idx >= 0:
            self._error_label.config(text="")
            self._show_page(prev_idx)

    def _cancel(self):
        if messagebox.askyesno(
            "Cancel Setup",
            "Are you sure you want to cancel the jH_ANS installation?",
            icon="warning"
        ):
            self.destroy()

    # ── Public API for pages ───────────────────────────────────────────

    def set_next_enabled(self, enabled: bool):
        """Called by pages to enable/disable the Next button."""
        is_last = self._current_index == len(STEPS) - 1
        if not is_last:
            self._next_btn.config(state="normal" if enabled else "disabled")

    def set_nav_visible(self, back: bool = True, next_: bool = True, cancel: bool = True):
        """Show/hide nav buttons (used by install page)."""
        self._back_btn.config(state="normal" if back else "disabled")
        self._next_btn.config(state="normal" if next_ else "disabled")
        self._cancel_btn.config(state="normal" if cancel else "disabled")

    def collect_config(self) -> dict:
        """Merge values from all pages into a single config dict."""
        config = {}
        for page in self._pages:
            config.update(page.get_values())
        return config


def main():
    app = WizardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
