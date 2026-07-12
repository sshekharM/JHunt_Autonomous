"""LLM configuration page."""
import tkinter as tk
from tkinter import ttk
import webbrowser
from .base import WizardPage

OLLAMA_MODELS = ["llama3", "gemma2", "mistral", "codellama"]


class LLMPage(WizardPage):
    title = "LLM Settings"
    subtitle = "Choose the AI engine that powers job matching and analysis"

    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(
            body,
            text="jH_ANS uses a large language model to analyse job descriptions, "
                 "match your profile, and draft application materials.",
            bg="#FFFFFF", fg="#323130",
            font=("Segoe UI", 10), wraplength=560, justify="left"
        ).pack(anchor="w", pady=(0, 14))

        self._llm_choice = tk.StringVar(value="ollama")

        # --- Ollama option ---
        ollama_rb = tk.Radiobutton(
            body, text="Self-hosted (Ollama) — runs locally in Docker, free, private",
            variable=self._llm_choice, value="ollama",
            bg="#FFFFFF", fg="#323130", font=("Segoe UI", 10),
            command=self._on_choice_change, activebackground="#FFFFFF"
        )
        ollama_rb.pack(anchor="w")

        self._ollama_frame = tk.Frame(body, bg="#F3F2F1", padx=12, pady=10)
        self._ollama_frame.pack(fill="x", pady=(2, 10))

        model_row = tk.Frame(self._ollama_frame, bg="#F3F2F1")
        model_row.pack(anchor="w", pady=2)
        tk.Label(model_row, text="Model:", bg="#F3F2F1", fg="#323130",
                 font=("Segoe UI", 10), width=12, anchor="w").pack(side="left")
        self._model_var = tk.StringVar(value="llama3")
        self._model_combo = ttk.Combobox(
            model_row, textvariable=self._model_var,
            values=OLLAMA_MODELS, state="readonly", width=20
        )
        self._model_combo.pack(side="left")

        tk.Label(
            self._ollama_frame,
            text="Note: Requires NVIDIA GPU with 8 GB+ VRAM for best performance.\n"
                 "CPU-only mode is supported but significantly slower.",
            bg="#F3F2F1", fg="#605E5C",
            font=("Segoe UI", 9), justify="left"
        ).pack(anchor="w", pady=(6, 0))

        # --- Anthropic option ---
        anthropic_rb = tk.Radiobutton(
            body, text="Anthropic Claude API — cloud-based, higher quality, requires API key",
            variable=self._llm_choice, value="anthropic",
            bg="#FFFFFF", fg="#323130", font=("Segoe UI", 10),
            command=self._on_choice_change, activebackground="#FFFFFF"
        )
        anthropic_rb.pack(anchor="w")

        self._anthropic_frame = tk.Frame(body, bg="#F3F2F1", padx=12, pady=10)
        self._anthropic_frame.pack(fill="x", pady=(2, 0))

        key_row = tk.Frame(self._anthropic_frame, bg="#F3F2F1")
        key_row.pack(anchor="w", pady=2)
        tk.Label(key_row, text="API Key:", bg="#F3F2F1", fg="#323130",
                 font=("Segoe UI", 10), width=12, anchor="w").pack(side="left")
        self._api_key_var = tk.StringVar()
        self._api_key_entry = ttk.Entry(
            key_row, textvariable=self._api_key_var, width=45, show="*"
        )
        self._api_key_entry.pack(side="left")

        btn_row = tk.Frame(self._anthropic_frame, bg="#F3F2F1")
        btn_row.pack(anchor="w", pady=(6, 0))
        self._test_btn = ttk.Button(
            btn_row, text="Test API Key", command=self._test_api_key
        )
        self._test_btn.pack(side="left")
        self._test_result = tk.Label(
            btn_row, text="", bg="#F3F2F1", font=("Segoe UI", 9)
        )
        self._test_result.pack(side="left", padx=8)

        privacy_row = tk.Frame(self._anthropic_frame, bg="#F3F2F1")
        privacy_row.pack(anchor="w", pady=(6, 0))
        tk.Label(
            privacy_row,
            text="Your data is sent to Anthropic's servers for processing.  ",
            bg="#F3F2F1", fg="#605E5C", font=("Segoe UI", 9)
        ).pack(side="left")
        link = tk.Label(
            privacy_row, text="Privacy Policy ↗",
            bg="#F3F2F1", fg="#0078D4",
            font=("Segoe UI", 9, "underline"), cursor="hand2"
        )
        link.pack(side="left")
        link.bind("<Button-1>",
                  lambda e: webbrowser.open("https://www.anthropic.com/privacy"))

        self._on_choice_change()

    def _on_choice_change(self):
        choice = self._llm_choice.get()
        ollama_state = "normal" if choice == "ollama" else "disabled"
        anthropic_state = "normal" if choice == "anthropic" else "disabled"
        self._model_combo.config(state="readonly" if choice == "ollama" else "disabled")
        self._api_key_entry.config(state=anthropic_state)
        self._test_btn.config(state=anthropic_state)

    def _test_api_key(self):
        key = self._api_key_var.get().strip()
        if not key:
            self._test_result.config(text="Enter an API key first.", fg="#D13438")
            return
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}]
            )
            self._test_result.config(text="API key valid!", fg="#107C10")
        except ImportError:
            self._test_result.config(
                text="anthropic package not installed — key will be validated at startup",
                fg="#FF8C00"
            )
        except Exception as e:
            self._test_result.config(text=f"Invalid: {e}", fg="#D13438")

    def validate(self) -> tuple:
        choice = self._llm_choice.get()
        if choice == "anthropic":
            key = self._api_key_var.get().strip()
            if not key:
                return False, "An Anthropic API key is required when using the Claude API."
            if not key.startswith("sk-ant-"):
                return False, "API key should start with 'sk-ant-'. Please check your key."
        return True, ""

    def get_values(self) -> dict:
        return {
            "llm_choice": self._llm_choice.get(),
            "ollama_model": self._model_var.get(),
            "anthropic_api_key": self._api_key_var.get().strip(),
        }
