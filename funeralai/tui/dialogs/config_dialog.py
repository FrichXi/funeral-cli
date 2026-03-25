"""Configuration display dialog (read-only)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from funeralai.analyzer import PROVIDERS
from funeralai.config import PROVIDERS_ENV, load_config, get_api_key


class ConfigDialog(ModalScreen[None]):
    """Modal dialog showing current configuration (read-only)."""

    DEFAULT_CSS = """
    ConfigDialog {
        align: center middle;
    }

    #config-dialog-box {
        width: 58;
        max-height: 28;
        border: round $accent;
        background: transparent;
        padding: 1 2;
        overflow-y: auto;
    }

    #config-dialog-box #config-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS = [("escape", "dismiss_config", "Close")]

    def __init__(
        self,
        provider: str = "",
        model: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._provider = provider
        self._model = model

    def compose(self) -> ComposeResult:
        with Vertical(id="config-dialog-box"):
            yield Static("Configuration", id="config-title")
            yield Static(self._build_content(), id="config-content")

    def _build_content(self) -> str:
        config = load_config()
        lines: list[str] = []

        # Current provider/model
        lines.append(f"[bold]Provider:[/]  {self._provider or '-'}")
        lines.append(f"[bold]Model:[/]     {self._model or '-'}")
        lines.append("")

        # Saved API keys (masked)
        keys = config.get("keys", {})
        if keys:
            lines.append("[bold]Saved API keys:[/]")
            for prov, key in keys.items():
                if key:
                    masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
                    lines.append(f"  {prov}: {masked}")
            lines.append("")

        # Env vars detected
        import os
        env_found = []
        for prov, env_var in PROVIDERS_ENV.items():
            if os.environ.get(env_var, "").strip():
                env_found.append(f"  {prov} ({env_var})")
        if env_found:
            lines.append("[bold]Environment variables:[/]")
            lines.extend(env_found)
            lines.append("")

        # Language
        lang = config.get("lang", "auto")
        lines.append(f"[bold]UI Language:[/]  {lang}")

        # Theme
        theme = config.get("theme", "funeral")
        lines.append(f"[bold]Theme:[/]       {theme}")

        lines.append("")
        lines.append("[dim]Press Escape to close[/]")

        return "\n".join(lines)

    def action_dismiss_config(self) -> None:
        self.dismiss(None)
