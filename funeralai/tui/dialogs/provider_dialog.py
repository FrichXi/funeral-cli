"""Provider selection dialog.

Lists all 8 providers with key status. User can select an existing
configured provider or paste a new API key inline.
"""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from funeralai.analyzer import PROVIDERS
from funeralai.auth import (
    classify_provider_error,
    mask_key,
    validate_provider_credentials,
)
from funeralai.config import detect_provider_from_key, get_api_key, save_api_key
from funeralai.i18n import t

# Display order: Claude first (recommended), then rest
_PROVIDER_ORDER = [
    "anthropic", "openai", "deepseek", "gemini",
    "qwen", "kimi", "minimax", "zhipu",
]


class ProviderDialog(ModalScreen[tuple[str, str] | None]):
    """Provider selection modal.

    Dismisses with (provider, api_key) on selection, or None on cancel.
    """

    DEFAULT_CSS = """
    ProviderDialog {
        align: center middle;
    }
    #pd-container {
        width: 60;
        max-height: 80%;
        height: auto;
        border: thick $accent;
        background: transparent;
        padding: 1 2;
    }
    #pd-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    #pd-filter {
        width: 100%;
        margin-bottom: 1;
    }
    #pd-list {
        height: auto;
        max-height: 14;
        margin-bottom: 1;
    }
    #pd-key-section {
        margin-top: 1;
    }
    #pd-key-input {
        width: 100%;
        margin-bottom: 1;
    }
    #pd-status {
        margin-bottom: 1;
    }
    #pd-btn-row {
        height: 3;
        align: center middle;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        current_provider: str = "",
        status_message: str = "",
    ) -> None:
        super().__init__()
        self._current = current_provider
        self._filter_text = ""
        self._pending_provider = ""
        self._status_message = status_message

    def compose(self) -> ComposeResult:
        with Vertical(id="pd-container"):
            yield Label(t("dlg_provider_title"), id="pd-title")
            yield Input(placeholder="Filter...", id="pd-filter")
            yield OptionList(id="pd-list")
            yield Static("", id="pd-status")
            # Key input for unconfigured providers
            yield Static("", id="pd-key-section", classes="hidden")
            yield Input(placeholder="sk-...", id="pd-key-input", classes="hidden")
            with Vertical(id="pd-btn-row"):
                yield Button("Cancel", id="pd-cancel", variant="default")

    def on_mount(self) -> None:
        self._refresh_list()
        if self._status_message:
            self.query_one("#pd-status", Static).update(self._status_message)
        self.query_one("#pd-filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "pd-filter":
            self._filter_text = event.value.strip().lower()
            self._refresh_list()

    def _refresh_list(self) -> None:
        """Rebuild the provider option list based on filter."""
        ol = self.query_one("#pd-list", OptionList)
        ol.clear_options()
        for name in _PROVIDER_ORDER:
            if name not in PROVIDERS:
                continue
            model = PROVIDERS[name]["default_model"]
            has_key = bool(get_api_key(name))
            status_mark = "[green]\u2713[/]" if has_key else "[dim]\u2717[/]"
            display = f"{status_mark} {name} ({model})"
            if name == self._current:
                display += "  [bold]\u25c0[/]"

            # Apply filter
            if self._filter_text and self._filter_text not in name and self._filter_text not in model.lower():
                continue

            ol.add_option(Option(display, id=name))

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle provider selection."""
        provider = str(event.option.id)
        key = get_api_key(provider)
        if key:
            await self._validate_and_accept(provider, key, save=False)
        else:
            # No key — show inline key input
            self._show_key_input(provider)

    def _show_key_input(
        self,
        provider: str,
        status_message: str | None = None,
    ) -> None:
        """Show API key input for an unconfigured provider."""
        status = self.query_one("#pd-status", Static)
        status.update(status_message or f"Enter API key for {provider}:")

        key_input = self.query_one("#pd-key-input", Input)
        key_input.display = True
        key_input.value = ""
        key_input.focus()

        # Store which provider we're configuring
        self._pending_provider = provider

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pd-key-input":
            key = event.value.strip()
            if not key:
                return
            provider = getattr(self, "_pending_provider", None)
            if not provider:
                # Try auto-detect
                provider = detect_provider_from_key(key)
            if provider:
                await self._validate_and_accept(provider, key, save=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pd-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def _validate_and_accept(
        self,
        provider: str,
        key: str,
        *,
        save: bool,
    ) -> None:
        """Validate a provider key before dismissing the dialog."""
        self._set_busy(True, t("setup_validating", provider=provider))
        model = PROVIDERS[provider]["default_model"]

        try:
            await asyncio.to_thread(
                validate_provider_credentials,
                provider,
                key,
                model,
            )
        except Exception as exc:
            issue = classify_provider_error(
                exc,
                provider=provider,
                model=model,
            )
            if issue.category in {"auth", "missing_key"}:
                self._set_busy(False, issue.message)
                self._show_key_input(
                    provider,
                    f"{issue.message}\nEnter API key for {provider}:",
                )
                return

            if save:
                save_api_key(provider, key)
                self.query_one("#pd-status", Static).update(
                    t("setup_saved_unverified", provider=provider)
                )
            status_text = str(self.query_one("#pd-status", Static).render())
            self._set_busy(False, status_text)
            self.dismiss((provider, key))
            return

        if save:
            save_api_key(provider, key)
            self.query_one("#pd-status", Static).update(
                t("key_saved", provider=provider, masked_key=mask_key(key))
            )
        status_text = str(self.query_one("#pd-status", Static).render())
        self._set_busy(False, status_text)
        self.dismiss((provider, key))

    def _set_busy(self, busy: bool, status: object) -> None:
        """Disable controls while validation is running."""
        self.query_one("#pd-status", Static).update(status)
        for selector, widget_type in (
            ("#pd-filter", Input),
            ("#pd-list", OptionList),
            ("#pd-key-input", Input),
            ("#pd-cancel", Button),
        ):
            try:
                self.query_one(selector, widget_type).disabled = busy
            except Exception:
                pass
