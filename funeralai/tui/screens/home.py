"""Home screen — the main landing screen of the TUI.

Layout (Claude Code style):
  - Top rule with version
  - Centered logo
  - Info line: provider (model) · cwd
  - Centered tips (toggleable)
  - PromptInput docked to bottom
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Static

from funeralai import __version__
from funeralai.i18n import t
from funeralai.tui.intent import parse_intent
from funeralai.tui.slash import build_slash_intent, dispatch_standard_intent
from funeralai.tui.widgets.logo import Logo
from funeralai.tui.widgets.prompt_input import PromptInput, PromptSubmitted, SlashCommand
from funeralai.tui.widgets.tips import Tips


class HomeScreen(Screen):
    """Main home screen with logo, input prompt, and tips.

    Layout (Claude Code style):
      - Top rule line with version
      - Top/bottom spacers (1fr) for vertical centering
      - Logo, info line, and tips centered in the middle
      - PromptInput docked to bottom (always visible)
    """

    BINDINGS = [
        ("ctrl+t", "toggle_tips", "Toggle tips"),
    ]

    def compose(self) -> ComposeResult:
        # Main content area — spacers push logo+tips to vertical center
        with Vertical(id="home-main"):
            yield Static(
                f"╶─── Funeral CLI v{__version__} {'─' * 60}",
                id="home-top-rule",
            )
            yield Static("", id="spacer-top")
            with Center():
                yield Logo(id="logo", first_run=self._is_first_run())
            with Center():
                yield Static("", id="home-info")
            with Center():
                yield Tips(id="tips")
            yield Static("", id="spacer-bottom")
        # PromptInput: dock bottom via its DEFAULT_CSS (always visible)
        yield PromptInput()

    def _is_first_run(self) -> bool:
        """Check if this is the first run (user hasn't completed setup)."""
        return self.app.state.needs_setup

    def on_mount(self) -> None:
        self._update_info()
        self.query_one(PromptInput).focus()

    # -- event handlers -------------------------------------------------------

    def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        """Handle plain text input from the prompt."""
        intent = parse_intent(event.value)
        if dispatch_standard_intent(
            self.app,
            self.app.state,
            intent,
            exit_action=self.app.exit,
            clear_action=lambda: None,
        ):
            return
        self._handle_intent(intent)

    def on_slash_command(self, event: SlashCommand) -> None:
        """Handle slash command from prompt input."""
        intent = build_slash_intent(event.command, event.arg)
        if dispatch_standard_intent(
            self.app,
            self.app.state,
            intent,
            exit_action=self.app.exit,
            clear_action=lambda: None,
            status_action=lambda msg, style: self.notify(
                msg.strip(),
                severity="error" if "red" in style else "information",
            ),
        ):
            return
        self._handle_intent(intent)

    def _handle_intent(self, intent) -> None:
        """Route parsed intent to the appropriate handler."""
        state = self.app.state

        if intent.type == "exit":
            self.app.exit()
            return

        if intent.type == "help":
            self.app.action_show_help()
            return

        if intent.type == "clear_screen":
            return

        if intent.type == "show_config":
            self.app.action_show_config()
            return

        if intent.type == "show_history":
            self.app.action_show_history()
            return

        if intent.type == "export_markdown":
            self.app.action_export_markdown()
            return

        if intent.type == "switch_theme":
            self.app.action_switch_theme()
            return

        if intent.type == "switch_provider":
            self.app.action_switch_provider(intent.provider)
            return

        if intent.type == "switch_model":
            self.app.action_switch_model(intent.model)
            return

        if intent.type == "switch_lang":
            self.app.action_switch_lang(intent.lang)
            return

        if intent.type in (
            "analyze_github",
            "analyze_web",
            "analyze_file",
            "analyze_text",
            "analyze_batch",
            "vote",
            "retry",
        ):
            # Push session screen for analysis tasks
            self.app.start_analysis(intent)
            return

        if intent.type == "chat":
            if not state.has_provider:
                self.notify(t("footer_no_provider"), severity="error")
                return
            self.app.start_analysis(intent)
            return

        if intent.type == "unknown_command":
            self.notify(
                f"Unknown command: {intent.raw}",
                severity="error",
            )
            return

        if intent.type == "unclear":
            self.notify(t("unclear_default"), severity="information")
            return

    # -- tips toggle -----------------------------------------------------------

    def action_toggle_tips(self) -> None:
        tips = self.query_one("#tips", Tips)
        tips.display = not tips.display

    # -- info line -------------------------------------------------------------

    def _update_info(self) -> None:
        """Update the info line below the logo."""
        state = self.app.state
        info = self.query_one("#home-info", Static)
        if state.has_provider:
            info.update(f"{state.provider_display} · {self._cwd_display()}")
        else:
            info.update(f"{t('footer_no_provider')} · {self._cwd_display()}")

    def _cwd_display(self) -> str:
        """Shorten cwd for display, replacing home dir with ~."""
        cwd = os.getcwd()
        home = str(Path.home())
        if cwd.startswith(home):
            return "~" + cwd[len(home):]
        return cwd

    def refresh_info(self) -> None:
        """Public method to refresh info after state changes."""
        self._update_info()

    # Backward compat alias
    refresh_footer = refresh_info
