"""FuneralApp — main Textual application for the TUI.

Entry point: ``run_app()`` creates and runs the app.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from textual.app import App

from funeralai.i18n import init_lang
from funeralai.tui.commands import FuneralCommands
from funeralai.tui.intent import Intent
from funeralai.tui.screens.home import HomeScreen
from funeralai.tui.state import AppState
from funeralai.tui.theme import (
    Theme,
    detect_terminal_background,
    get_theme_from_config,
)


class FuneralApp(App):
    """Main TUI application."""

    CSS_PATH = "app.tcss"
    COMMANDS = {FuneralCommands}

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        # Initialize theme BEFORE super().__init__() because Textual calls
        # get_css_variables() during stylesheet initialization in super().__init__().
        mode, terminal_bg = detect_terminal_background()
        self._terminal_bg = terminal_bg  # actual terminal hex color, or None
        theme_name = get_theme_from_config()
        self.theme_obj = Theme(theme_name, mode)
        self.state = AppState()
        super().__init__()

    def on_mount(self) -> None:
        """Initialize language, state, theme, and push the home screen."""
        # 1. Language
        init_lang()

        # 2. State from config
        self.state.init_from_config()

        # 3. Theme (already initialized in __init__, just refresh CSS)
        self._apply_theme()

        # 4. Push home screen
        self.install_screen(HomeScreen, name="home")
        self.push_screen("home")

        # 5. If user hasn't explicitly configured (first run), push setup modal
        #    — even if env vars provide a provider, let user confirm or pick another
        if self.state.needs_setup:
            self._push_setup()

    # -- theme ----------------------------------------------------------------

    def get_css_variables(self) -> dict[str, str]:
        """Inject our theme colors as CSS variables.

        Variable names match what app.tcss expects: $background, $text, etc.
        Background-related variables use the detected terminal background
        so Textual renders the same color as the terminal (visually transparent).
        """
        variables = super().get_css_variables()
        if self.theme_obj:
            colors = self.theme_obj.colors
            for slot in type(colors).__dataclass_fields__:
                val = getattr(colors, slot)
                css_name = slot.replace("_", "-")
                variables[css_name] = val
            variables["terminal-background"] = self._terminal_bg or colors.background
            variables["surface"] = colors.background_panel
            variables["surface-elevated"] = colors.background_element
        return variables

    def _apply_theme(self) -> None:
        """Refresh CSS and logo after theme change."""
        self.refresh_css()
        self._refresh_home_logo()

    def _refresh_home_logo(self) -> None:
        """Re-render the logo on the home screen to pick up new theme colors."""
        try:
            home = self.get_screen("home")
            from funeralai.tui.widgets.logo import Logo
            logo = home.query_one(Logo)
            logo.refresh_logo()
        except Exception:
            pass

    # -- setup ----------------------------------------------------------------

    def _apply_provider_choice(
        self,
        provider: str,
        key: str,
        *,
        configured: bool = True,
    ) -> None:
        """Apply a provider choice and refresh dependent UI."""
        self.state.configure_provider(provider, key, configured=configured)
        self._refresh_home_footer()

    def _push_setup(self, on_success: Callable[[], None] | None = None) -> None:
        """Push the first-run setup modal."""
        from funeralai.tui.screens.setup import SetupScreen

        def on_setup_dismiss(result: tuple[str, str] | None) -> None:
            if result:
                provider, key = result
                self._apply_provider_choice(provider, key, configured=True)
                if on_success:
                    on_success()

        self.push_screen(SetupScreen(), callback=on_setup_dismiss)

    # -- actions exposed to screens -------------------------------------------

    def _refresh_home_footer(self) -> None:
        """Refresh the home screen info line if it's installed."""
        try:
            home = self.get_screen("home")
            if hasattr(home, "refresh_info"):
                home.refresh_info()
            elif hasattr(home, "refresh_footer"):
                home.refresh_footer()
        except Exception:
            pass

    def action_show_help(self) -> None:
        """Show help dialog."""
        from funeralai.tui.dialogs.help_dialog import HelpDialog
        self.push_screen(HelpDialog())

    def action_show_config(self) -> None:
        """Show config dialog."""
        from funeralai.tui.dialogs.config_dialog import ConfigDialog
        self.push_screen(ConfigDialog(
            provider=self.state.provider,
            model=self.state.default_model,
        ))

    def action_show_history(self) -> None:
        """Show analysis history (notification for now)."""
        count = len(self.state.analyses)
        self.notify(f"{count} analyses in this session.", title="History")

    def _post_screen_status(
        self,
        lines: list[tuple[str, str]],
        *,
        fallback_message: str,
        fallback_severity: str = "information",
        fallback_title: str | None = None,
    ) -> None:
        """Prefer inline status in the active screen, otherwise show a toast."""
        add_status = getattr(self.screen, "_add_status", None)
        if callable(add_status):
            for text, style in lines:
                add_status(text, style=style)
            return

        self.notify(
            fallback_message,
            severity=fallback_severity,
            title=fallback_title,
        )

    def action_export_markdown(self) -> None:
        """Export the current report to a Markdown file."""
        if self.state.current_result is None:
            self._post_screen_status(
                [("  没有可导出的报告。", "bold red")],
                fallback_message="No report available to export.",
                fallback_severity="error",
            )
            return

        try:
            from funeralai.exporting import export_markdown

            path = export_markdown(
                self.state.current_result,
                inspection=self.state.last_inspection,
                input_type=self.state.last_input_type or "local",
                base_dir=Path.cwd() / "exports",
            )
        except Exception as exc:
            self._post_screen_status(
                [(f"  导出失败: {exc}", "bold red")],
                fallback_message=f"Export failed: {exc}",
                fallback_severity="error",
                fallback_title="Export",
            )
            return

        resolved = path.resolve()
        self._post_screen_status(
            [
                ("", "dim"),
                ("  已导出 Markdown 报告", "bold"),
                (f"  {resolved}", "dim"),
            ],
            fallback_message=f"Markdown exported: {resolved}",
            fallback_title="Export",
        )

    def action_switch_theme(self) -> None:
        """Show theme selection dialog."""
        from funeralai.tui.dialogs.theme_dialog import ThemeDialog

        def on_theme_dismiss(result: str | None) -> None:
            if result and self.theme_obj:
                self.theme_obj = Theme(result, self.theme_obj.mode)
                self._apply_theme()

        self.push_screen(ThemeDialog(), callback=on_theme_dismiss)

    def action_switch_provider(self, provider: str = "") -> None:
        """Switch provider — inline if name given, dialog otherwise."""
        if provider and self.state.switch_provider(provider):
            self._refresh_home_footer()
            self.notify(f"Switched to {self.state.provider_display}")
            return

        from funeralai.tui.dialogs.provider_dialog import ProviderDialog

        def on_provider_dismiss(result: tuple[str, str] | None) -> None:
            if result:
                prov, key = result
                self._apply_provider_choice(prov, key, configured=True)
                self.notify(f"Switched to {self.state.provider_display}")

        self.push_screen(
            ProviderDialog(current_provider=self.state.provider),
            callback=on_provider_dismiss,
        )

    def action_switch_model(self, model: str = "") -> None:
        """Switch model."""
        if model:
            self.state.switch_model(model)
            self._refresh_home_footer()
            self.notify(f"Model set to {model}")
        else:
            self.notify("Usage: /model <model-name>", title="Model")

    def action_switch_lang(self, lang: str = "") -> None:
        """Switch UI language."""
        if lang in ("zh", "en"):
            from funeralai.i18n import set_lang
            set_lang(lang)
            self.notify(f"Language set to {lang}")
        else:
            self.notify("Usage: /lang zh or /lang en", title="Language")

    def action_vote(self) -> None:
        """Show vote dialog for multi-model voting."""
        from funeralai.tui.dialogs.vote_dialog import VoteDialog

        if not self.state.can_vote():
            self.notify("No previous analysis to vote on.", severity="warning")
            return

        def on_vote_dismiss(result: list[str] | None) -> None:
            if result and len(result) >= 2:
                vote_intent = Intent(
                    type="vote", providers=result, raw="/vote"
                )
                self.start_analysis(vote_intent)

        self.push_screen(VoteDialog(), callback=on_vote_dismiss)

    def action_new_analysis(self) -> None:
        """Focus the prompt input for a new analysis."""
        try:
            home = self.get_screen("home")
            from funeralai.tui.widgets.prompt_input import PromptInput
            home.query_one(PromptInput).focus()
        except Exception:
            pass

    def action_clear_screen(self) -> None:
        """Clear screen — pop back to home."""
        try:
            while len(self.screen_stack) > 1:
                self.pop_screen()
        except Exception:
            pass

    def action_retry_analysis(self) -> None:
        """Retry the last analysis."""
        if not self.state.can_retry():
            self.notify("Nothing to retry.", severity="warning")
            return
        retry_intent = Intent(type="retry", raw="retry")
        self.start_analysis(retry_intent)

    def start_analysis(self, intent: Intent) -> None:
        """Push a SessionScreen to run the analysis end-to-end."""
        from funeralai.tui.screens.session import SessionScreen

        state = self.state

        # Pre-flight checks
        if intent.type == "vote" and not state.can_vote():
            self.notify("No previous analysis to vote on.", severity="warning")
            return
        if intent.type == "retry" and not state.can_retry():
            self.notify("Nothing to retry.", severity="warning")
            return

        if not state.has_provider:
            self._push_setup(lambda: self.start_analysis(intent))
            return

        self.push_screen(SessionScreen(intent=intent, state=state))


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


def run_app() -> None:
    """Create and run the FuneralApp."""
    app = FuneralApp()
    app.run()
