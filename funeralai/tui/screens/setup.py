"""First-run setup modal — API key configuration.

Checks env vars, Codex CLI auth, then prompts the user to paste a key
if nothing is detected. Auto-detects provider from key prefix; falls back
to manual provider selection.
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
from funeralai.config import (
    detect_provider_from_key,
    save_api_key,
    scan_env_keys,
    try_codex_auth,
)
from funeralai.i18n import t


# Provider display order: Claude first (recommended), then rest alphabetically
_PROVIDER_ORDER = ["anthropic", "openai", "deepseek", "gemini", "qwen", "kimi", "minimax", "zhipu"]


class SetupScreen(ModalScreen[tuple[str, str] | None]):
    """First-run API key configuration modal.

    Dismisses with (provider, api_key) on success, or None on cancel.
    """

    DEFAULT_CSS = """
    SetupScreen {
        align: center middle;
    }
    #setup-container {
        width: 64;
        max-height: 80%;
        height: auto;
        border: thick $accent;
        background: transparent;
        padding: 1 2;
    }
    #setup-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    #setup-status {
        margin-bottom: 1;
    }
    #setup-key-input {
        width: 100%;
        margin-bottom: 1;
    }
    #setup-prompt {
        margin-bottom: 0;
    }
    #setup-provider-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    #setup-providers {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
    }
    #setup-detected-row {
        height: auto;
        margin-bottom: 1;
    }
    #setup-use-detected {
        width: 100%;
        margin-bottom: 1;
    }
    #setup-configure-other {
        width: 100%;
    }
    #setup-btn-row {
        height: 3;
        align: center middle;
    }
    #setup-cancel {
        margin-left: 2;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._detected: tuple[str, str] | None = None
        self._pending_key: str = ""  # key waiting for provider selection
        self._dismissed: bool = False  # guard against double-dismiss from timer races

    def _safe_dismiss(self, result: tuple[str, str] | None) -> None:
        """Dismiss the screen at most once, preventing timer race conditions."""
        if self._dismissed:
            return
        self._dismissed = True
        self.dismiss(result)

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-container"):
            yield Label(t("dlg_setup_title"), id="setup-title")
            yield Static("", id="setup-status")
            # Detected env/codex: two action buttons
            with Vertical(id="setup-detected-row"):
                yield Button(
                    t("setup_use_detected"),
                    id="setup-use-detected",
                    variant="primary",
                )
                yield Button(
                    t("setup_configure_other"),
                    id="setup-configure-other",
                    variant="default",
                )
            # Manual key input
            yield Static(t("setup_paste_key"), id="setup-prompt")
            yield Input(placeholder="sk-...", id="setup-key-input")
            yield Static(
                t("setup_select_provider"),
                id="setup-provider-label",
                classes="hidden",
            )
            yield OptionList(id="setup-providers")
            with Vertical(id="setup-btn-row"):
                yield Button("Cancel", id="setup-cancel", variant="default")

    def on_mount(self) -> None:
        """Check for existing credentials on mount."""
        status = self.query_one("#setup-status", Static)
        providers_list = self.query_one("#setup-providers", OptionList)
        providers_list.display = False

        # Hide detected-row by default; show only when env/codex found
        detected_row = self.query_one("#setup-detected-row")
        detected_row.display = False

        # 1. Check env vars
        env_result = scan_env_keys()
        if env_result:
            provider, key = env_result
            status.update(t("setup_env_detected", provider=provider))
            self._detected = (provider, key)
            # Show detected buttons, hide manual input
            detected_row.display = True
            self.query_one("#setup-prompt", Static).display = False
            self.query_one("#setup-key-input", Input).display = False
            self.query_one("#setup-use-detected", Button).focus()
            return

        # 2. Check Codex CLI auth
        codex_result = try_codex_auth()
        if codex_result:
            provider, key = codex_result
            status.update(t("codex_detected"))
            self._detected = (provider, key)
            detected_row.display = True
            self.query_one("#setup-prompt", Static).display = False
            self.query_one("#setup-key-input", Input).display = False
            self.query_one("#setup-use-detected", Button).focus()
            return

        # 3. Nothing found: show input
        status.update(t("no_api_key"))
        self.query_one("#setup-key-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle API key paste."""
        if event.input.id != "setup-key-input":
            return

        key = event.value.strip()
        if not key:
            return

        # Try auto-detect provider
        provider = detect_provider_from_key(key)
        if provider:
            await self._validate_and_accept(provider, key)
            return

        # Can't auto-detect: show provider selection
        self._pending_key = key
        self._show_provider_selection()

    def _show_provider_selection(self) -> None:
        """Show provider list for manual selection."""
        self.query_one("#setup-key-input", Input).display = False
        self.query_one("#setup-prompt", Static).display = False

        label = self.query_one("#setup-provider-label", Static)
        label.display = True

        providers_list = self.query_one("#setup-providers", OptionList)
        providers_list.clear_options()
        for name in _PROVIDER_ORDER:
            if name in PROVIDERS:
                model = PROVIDERS[name]["default_model"]
                display = f"{name} ({model})"
                if name == "anthropic":
                    display += "  [recommended]"
                providers_list.add_option(Option(display, id=name))
        providers_list.display = True
        providers_list.focus()

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle provider selection from list."""
        provider = str(event.option.id)
        key = self._pending_key
        if key and provider:
            await self._validate_and_accept(provider, key)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-cancel":
            self._safe_dismiss(None)
        elif event.button.id == "setup-use-detected":
            if self._detected:
                provider, key = self._detected
                await self._validate_and_accept(provider, key)
        elif event.button.id == "setup-configure-other":
            # Switch to manual key input
            self.query_one("#setup-detected-row").display = False
            self.query_one("#setup-prompt", Static).display = True
            self.query_one("#setup-key-input", Input).display = True
            self.query_one("#setup-status", Static).update(t("no_api_key"))
            self.query_one("#setup-key-input", Input).focus()

    def action_cancel(self) -> None:
        self._safe_dismiss(None)

    async def _validate_and_accept(self, provider: str, key: str) -> None:
        """Validate the credential before saving it."""
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
                self._show_manual_reconfigure(provider, issue.message)
                return

            save_api_key(provider, key)
            self._set_busy(False, t("setup_saved_unverified", provider=provider))
            self.set_timer(0.3, lambda: self._safe_dismiss((provider, key)))
            return

        save_api_key(provider, key)
        self._set_busy(
            False,
            t("key_saved", provider=provider, masked_key=mask_key(key)),
        )
        self.set_timer(0.3, lambda: self._safe_dismiss((provider, key)))

    def _show_manual_reconfigure(self, provider: str, message: str) -> None:
        """Reveal manual entry again after a bad detected/saved key."""
        self.query_one("#setup-detected-row").display = False
        self.query_one("#setup-prompt", Static).display = True
        key_input = self.query_one("#setup-key-input", Input)
        key_input.display = True
        key_input.value = ""
        key_input.focus()
        self._pending_key = ""
        self.query_one("#setup-status", Static).update(
            f"{message}\n{t('setup_reauth_prompt', provider=provider)}"
        )

    def _set_busy(self, busy: bool, status: str) -> None:
        """Disable controls while validation is in progress."""
        self.query_one("#setup-status", Static).update(status)
        for selector, widget_type in (
            ("#setup-use-detected", Button),
            ("#setup-configure-other", Button),
            ("#setup-key-input", Input),
            ("#setup-providers", OptionList),
            ("#setup-cancel", Button),
        ):
            try:
                self.query_one(selector, widget_type).disabled = busy
            except Exception:
                pass
