"""Analysis session screen — the main work view.

Displays analysis progress (spinner + status), results (report), and handles
new input via PromptInput. Question-answer flow is embedded inline.

Layout:
    +--------------------------------------------------+
    |  [VerticalScroll - analysis output area]          |
    |  StatusMessage / AnalysisSpinner / ReportView     |
    +--------------------------------------------------+
    |  [PromptInput - full width]                       |
    +--------------------------------------------------+
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen

from funeralai.auth import (
    classify_provider_error,
    find_vote_blocking_issues,
    is_blocking_credential_error,
    replace_vote_provider,
)
from funeralai.i18n import t
from funeralai.tui.intent import Intent, parse_intent
from funeralai.tui.dispatch import (
    dispatch_batch,
    dispatch_chat,
    dispatch_file,
    dispatch_github,
    dispatch_text,
    dispatch_vote,
    dispatch_web,
)
from funeralai.tui.slash import build_slash_intent, dispatch_standard_intent
from funeralai.tui.state import (
    AppState,
    STATUS_ASKING,
    STATUS_CHATTING,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_EXTRACTING,
    STATUS_IDLE,
    STATUS_INSPECTING,
    STATUS_JUDGING,
)
from funeralai.tui.widgets.prompt_input import PromptInput, PromptSubmitted, SlashCommand
from funeralai.tui.widgets.report import ChatMessageView, ReportView, StatusMessage, VoteReportView
from funeralai.tui.widgets.spinner import AnalysisSpinner


# Status key -> i18n key mapping
_STATUS_I18N = {
    STATUS_INSPECTING: "status_inspecting_github",
    STATUS_EXTRACTING: "status_extracting",
    STATUS_ASKING: "status_asking",
    STATUS_JUDGING: "status_judging",
    STATUS_DONE: "status_done",
}


class SessionScreen(Screen):
    """Analysis view with scrollable results and input."""

    DEFAULT_CSS = """
    SessionScreen {
        layout: vertical;
    }
    #session-scroll {
        height: 1fr;
        padding: 0 1;
    }
    #question-label {
        margin: 1 0 0 0;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("ctrl+c", "app.quit", "Quit"),
        ("ctrl+g", "cancel_analysis", "Cancel"),
    ]

    def __init__(
        self,
        intent: Intent,
        state: AppState,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._intent = intent
        self._state = state
        self._spinner: AnalysisSpinner | None = None
        self._analysis_worker = None
        self._question_mode = False

    # -- compose ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="session-scroll")
        yield PromptInput()

    # -- lifecycle -------------------------------------------------------------

    def on_mount(self) -> None:
        """Start the analysis dispatch."""
        # Show source info as first line in scroll area
        source = self._source_label()
        provider_info = self._state.provider_display
        self._add_status(f"Analysis: {source} · {provider_info}")
        self._add_status("")  # spacer

        spinner_text = self._spinner_text_for_intent(self._intent)
        self._show_spinner(spinner_text)
        self._analysis_worker = self.run_worker(
            self._run_analysis(), exclusive=True
        )

    # -- analysis dispatch -----------------------------------------------------

    async def _run_analysis(self) -> None:
        """Dispatch analysis based on intent type."""
        intent = self._intent
        state = self._state

        try:
            if intent.type == "chat":
                chat_text = intent.text or intent.raw.strip()
                self._update_spinner(t("status_chatting"))
                chat_result = await dispatch_chat(chat_text, state)

                self._remove_spinner()
                self._show_chat_reply(chat_result["reply"])

                if chat_result.get("action_intent"):
                    self._apply_chat_action(chat_result["action_intent"])

                # Re-enable input and return early (skip normal result flow)
                self._set_input_enabled(True)
                return

            elif intent.type == "analyze_github":
                self._update_spinner(t("status_inspecting_github"))
                result = await dispatch_github(intent.url, state)
            elif intent.type == "analyze_web":
                self._update_spinner(t("status_inspecting_web"))
                result = await dispatch_web(intent.url, state)
            elif intent.type == "analyze_file":
                self._update_spinner(t("status_extracting"))
                result = await dispatch_file(intent.path, state)
            elif intent.type == "analyze_text":
                text = intent.text or intent.raw.strip()
                self._update_spinner(t("status_extracting"))
                result = await dispatch_text(text, state)
            elif intent.type == "analyze_batch":
                self._update_spinner(t("status_extracting"))
                result = await dispatch_batch(intent.paths, state)
            elif intent.type == "vote":
                self._update_spinner(t("status_judging"))
                result = await dispatch_vote(intent.providers, state)
                blocking_vote_issues = find_vote_blocking_issues(result)
                if blocking_vote_issues:
                    await self._recover_vote_credentials(blocking_vote_issues[0])
                    return
            else:
                self._remove_spinner()
                self._add_status(f"Unknown intent: {intent.type}", style="bold red")
                return

            # Analysis complete: show report
            self._remove_spinner()
            self._show_result(result, intent)

        except asyncio.CancelledError:
            self._remove_spinner()
            self._add_status(f"  {t('status_cancelled')}", style="bold yellow")
            self._state.status = STATUS_IDLE
            self._state.status_detail = ""
            self._set_input_enabled(True)
            raise
        except Exception as e:
            self._remove_spinner()
            friendly = self._format_error(e)
            self._add_status(f"  Error: {friendly}", style="bold red")
            self._state.status = STATUS_ERROR
            self._state.status_detail = str(e)
            if is_blocking_credential_error(e):
                await self._recover_credentials(friendly)
                return

        # Re-enable input
        self._set_input_enabled(True)

    # -- result rendering ------------------------------------------------------

    def _show_result(self, result: dict, intent: Intent) -> None:
        """Mount the appropriate report widget."""
        try:
            scroll = self.query_one("#session-scroll", VerticalScroll)
        except Exception:
            return
        input_type = _intent_to_input_type(intent)
        inspection = self._state.last_inspection

        if intent.type == "vote":
            widget = VoteReportView(
                vote_result=result,
                inspection=inspection,
                input_type=input_type,
            )
        else:
            widget = ReportView(
                result=result,
                inspection=inspection,
                input_type=input_type,
            )

        scroll.mount(widget)
        self._add_status(t("status_done"), style="bold green")
        self._scroll_to_bottom()

    def _show_chat_reply(self, reply: str) -> None:
        """Mount a ChatMessageView for a chat response."""
        try:
            scroll = self.query_one("#session-scroll", VerticalScroll)
        except Exception:
            return
        scroll.mount(ChatMessageView(reply))
        self._scroll_to_bottom()

    def _apply_chat_action(self, action_intent: Intent) -> None:
        """Execute a chat-extracted ACTION (provider/model/lang switch)."""
        if action_intent.type == "switch_provider":
            name = action_intent.provider
            if name and self._state.switch_provider(name):
                model = self._state.default_model
                self._add_status(
                    t("switched", provider=name, model=model),
                    style="bold green",
                )
                self._update_footer()
            else:
                self._add_status(
                    f"  No API key for {name}.", style="bold red"
                )

        elif action_intent.type == "switch_model":
            model = action_intent.model
            if model:
                self._state.switch_model(model)
                self._add_status(f"  Model: {model}", style="bold green")
                self._update_footer()

        elif action_intent.type == "switch_lang":
            lang = action_intent.lang
            if lang in ("zh", "en"):
                from funeralai.i18n import set_lang
                set_lang(lang)
                self._add_status(
                    f"  Language: {lang}", style="bold green"
                )

    # -- spinner management ----------------------------------------------------

    def _show_spinner(self, text: str) -> None:
        """Add spinner to the scroll area."""
        try:
            scroll = self.query_one("#session-scroll", VerticalScroll)
        except Exception:
            return
        self._spinner = AnalysisSpinner(text=text)
        scroll.mount(self._spinner)
        self._scroll_to_bottom()
        self._set_input_enabled(False, reason=self._input_pause_reason(text))

    def _update_spinner(self, text: str) -> None:
        """Update spinner text, reflecting status change."""
        if self._spinner:
            self._spinner.set_text(text)
        self._state.status_detail = text
        try:
            prompt = self.query_one(PromptInput)
            if prompt.disabled:
                prompt.set_disabled_reason(self._input_pause_reason(text))
        except Exception:
            pass

    def _remove_spinner(self) -> None:
        """Remove spinner from scroll area."""
        if self._spinner:
            self._spinner.remove()
            self._spinner = None

    # -- status / scroll helpers -----------------------------------------------

    def _add_status(self, text: str, style: str = "dim") -> None:
        """Add a status message line to the scroll area."""
        try:
            scroll = self.query_one("#session-scroll", VerticalScroll)
        except Exception:
            return
        scroll.mount(StatusMessage(text, style=style))
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Auto-scroll the output area to the bottom."""
        try:
            scroll = self.query_one("#session-scroll", VerticalScroll)
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _set_input_enabled(self, enabled: bool, reason: str | None = None) -> None:
        """Enable or disable the prompt input."""
        try:
            prompt = self.query_one(PromptInput)
            prompt.set_disabled_reason(reason if not enabled else None)
            prompt.disabled = not enabled
            if enabled:
                prompt.focus()
        except Exception:
            pass

    def _input_pause_reason(self, status_text: str) -> str:
        """Build the disabled-input hint shown in the prompt."""
        return t("input_paused", status=status_text)

    def _spinner_text_for_intent(self, intent: Intent) -> str:
        """Return the initial spinner text for a given intent."""
        if intent.type == "chat":
            return t("status_chatting")
        if intent.type == "vote":
            return t("status_judging")
        if intent.type == "analyze_github":
            return t("status_inspecting_github")
        if intent.type == "analyze_web":
            return t("status_inspecting_web")
        return t("status_extracting")

    def _start_intent_in_place(self, intent: Intent) -> None:
        """Run a new analysis in the current session, preserving history."""
        self._intent = intent
        self._add_status("")
        self._add_status(f"  New analysis: {self._source_label_from(intent)}")
        self._show_spinner(self._spinner_text_for_intent(intent))
        self._analysis_worker = self.run_worker(
            self._run_analysis(), exclusive=True
        )

    def action_cancel_analysis(self) -> None:
        """Cancel the active worker and restore the prompt."""
        worker = self._analysis_worker
        if worker is None or not getattr(worker, "is_running", False):
            self._add_status(f"  {t('status_no_active_analysis')}", style="dim")
            return
        self._add_status(f"  {t('status_cancelling')}", style="bold yellow")
        self._update_spinner(t("status_cancelling"))
        worker.cancel()

    # -- input handling --------------------------------------------------------

    def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        """Handle new input from the user."""
        text = event.value.strip()
        if not text:
            return

        # Parse intent using the standalone pure function
        intent = parse_intent(text, last_input_type=self._state.last_input_type)

        # Analysis intents: start a new analysis
        if intent.type in (
            "analyze_github",
            "analyze_web",
            "analyze_file",
            "analyze_batch",
            "analyze_text",
            "vote",
        ):
            self._start_intent_in_place(intent)
            return

        # Retry: re-run last analysis
        if intent.type == "retry":
            if self._state.can_retry():
                self._add_status("")
                self._add_status("  Retrying last analysis...")
                self._show_spinner(t("status_extracting"))
                self._analysis_worker = self.run_worker(
                    self._retry_analysis(), exclusive=True
                )
            else:
                self._add_status("  Nothing to retry.", style="dim")
            return

        # Switch provider inline
        if intent.type == "switch_provider":
            from funeralai.analyzer import PROVIDERS

            name = intent.provider
            if name and name in PROVIDERS:
                if self._state.switch_provider(name):
                    model = self._state.default_model
                    self._add_status(
                        t("switched", provider=name, model=model),
                        style="bold green",
                    )
                    self._update_footer()
                    # Auto-retry with new provider
                    if self._state.can_retry():
                        self._show_spinner(t("status_extracting"))
                        self._analysis_worker = self.run_worker(
                            self._retry_analysis(), exclusive=True
                        )
                else:
                    self._add_status(
                        f"  No API key for {name}. Use /config to set up.",
                        style="bold red",
                    )
            return

        # Exit: go back to home
        if intent.type == "exit":
            self.app.pop_screen()
            return

        # Help, config, etc: show inline status
        if intent.type == "help":
            self._add_status("  /provider - switch provider")
            self._add_status("  /vote - multi-model vote")
            self._add_status("  /export - export current report as Markdown")
            self._add_status("  retry - re-run last analysis")
            self._add_status("  exit - back to home")
            return

        if intent.type == "export_markdown":
            self.app.action_export_markdown()
            return

        # Clear
        if intent.type == "clear_screen":
            self._clear_session_output()
            return

        # Chat: short text that isn't a command → send to LLM
        if intent.type == "chat":
            if not self._state.has_provider:
                self._add_status(t("footer_no_provider"), style="bold red")
                return
            self._intent = intent
            self._add_status("")  # spacer
            self._show_spinner(t("status_chatting"))
            self._analysis_worker = self.run_worker(
                self._run_analysis(), exclusive=True
            )
            return

        # Anything else: show hint
        self._add_status(t("unclear_default"), style="dim")

    def on_slash_command(self, event: SlashCommand) -> None:
        """Handle slash commands from prompt input."""
        intent = build_slash_intent(event.command, event.arg)
        if dispatch_standard_intent(
            self.app,
            self._state,
            intent,
            exit_action=self.app.pop_screen,
            clear_action=self._clear_session_output,
            status_action=self._add_status,
            start_vote_action=self._start_intent_in_place,
        ):
            return

        if intent.type == "unknown_command":
            self._add_status(
                f"  Unknown command: {event.command}",
                style="bold red",
            )
        elif intent.type == "unclear":
            self._add_status(t("unclear_default"), style="dim")

    # -- retry -----------------------------------------------------------------

    async def _retry_analysis(self) -> None:
        """Re-run the last analysis (e.g. after provider switch)."""
        state = self._state
        text = state.last_text
        if not text:
            self._remove_spinner()
            self._add_status("  Nothing to retry.", style="dim")
            self._set_input_enabled(True)
            return

        pv_map = {"file": 1, "text": 1, "github": 2, "web": 3}
        pv = pv_map.get(state.last_input_type or "", 1)

        from funeralai.analyzer import analyze

        try:
            self._update_spinner(t("status_extracting"))
            result = await asyncio.to_thread(
                analyze,
                text=text,
                api_key=state.api_key,
                model=state.model,
                provider=state.provider,
                prompt_version=pv,
                interactive=False,
                red_flags=state.last_red_flags,
            )
            state.record_analysis(result)

            self._remove_spinner()
            # Create a fake intent for display
            fake_intent = Intent(
                type=f"analyze_{state.last_input_type or 'text'}",
                raw=state.last_input or "",
            )
            self._show_result(result, fake_intent)

        except asyncio.CancelledError:
            self._remove_spinner()
            self._add_status(f"  {t('status_cancelled')}", style="bold yellow")
            self._state.status = STATUS_IDLE
            self._state.status_detail = ""
            self._set_input_enabled(True)
            raise
        except Exception as e:
            self._remove_spinner()
            friendly = self._format_error(e)
            self._add_status(f"  Error: {friendly}", style="bold red")
            if is_blocking_credential_error(e):
                await self._recover_credentials(friendly)
                return

        self._set_input_enabled(True)

    # -- footer update ---------------------------------------------------------

    def _update_footer(self) -> None:
        """No-op: footer removed in Claude Code style redesign."""
        pass

    def _clear_session_output(self) -> None:
        """Clear the visible session output without leaving the screen."""
        try:
            scroll = self.query_one("#session-scroll", VerticalScroll)
        except Exception:
            return
        scroll.remove_children()

    # -- error formatting ------------------------------------------------------

    def _format_error(self, error: Exception) -> str:
        """Format error for user-friendly display."""
        issue = classify_provider_error(
            error,
            provider=self._state.provider,
            model=self._state.default_model,
        )
        if issue.category != "unknown":
            return issue.message

        msg = str(error)

        # Fallback: show original but truncated
        if len(msg) > 150:
            msg = msg[:150] + "..."
        return msg

    async def _recover_credentials(self, message: str) -> None:
        """Open provider recovery flow after a bad or missing key."""
        from funeralai.tui.dialogs.provider_dialog import ProviderDialog

        prompt = t("setup_reauth_prompt", provider=self._state.provider or "当前 Provider")
        self._add_status(f"  {prompt}", style="bold")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[str, str] | None] = loop.create_future()

        def on_provider_dismiss(result: tuple[str, str] | None) -> None:
            if not future.done():
                future.set_result(result)

        self.app.push_screen(
            ProviderDialog(
                current_provider=self._state.provider,
                status_message=message,
            ),
            callback=on_provider_dismiss,
        )
        result = await future
        if not result:
            self._set_input_enabled(True)
            return

        provider, key = result
        self._state.configure_provider(provider, key, configured=True)
        self._update_footer()
        self._add_status(
            t("switched", provider=provider, model=self._state.default_model),
            style="bold green",
        )
        self._show_spinner(t("status_extracting"))
        self._analysis_worker = self.run_worker(
            self._retry_analysis(),
            exclusive=True,
        )

    async def _recover_vote_credentials(self, target) -> None:
        """Repair one broken provider inside a vote and rerun the vote."""
        from funeralai.tui.dialogs.provider_dialog import ProviderDialog

        self._remove_spinner()
        self._add_status(
            f"  Vote provider 需要修复: {target.issue.message}",
            style="bold red",
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[str, str] | None] = loop.create_future()

        def on_provider_dismiss(result: tuple[str, str] | None) -> None:
            if not future.done():
                future.set_result(result)

        self.app.push_screen(
            ProviderDialog(
                current_provider=target.provider,
                status_message=target.issue.message,
            ),
            callback=on_provider_dismiss,
        )
        result = await future
        if not result:
            self._set_input_enabled(True)
            return

        provider, key = result
        self._state.configure_provider(provider, key, configured=True)
        self._update_footer()

        if self._intent.type == "vote":
            self._intent.providers = replace_vote_provider(
                self._intent.providers,
                target.provider,
                provider,
            )
            if len(self._intent.providers) < 2:
                self._add_status(
                    "  修复后可用于投票的不同 provider 少于 2 个。",
                    style="bold red",
                )
                self._set_input_enabled(True)
                return

        self._add_status(
            f"  已修复 vote provider，重新投票: {', '.join(self._intent.providers)}",
            style="bold green",
        )
        self._show_spinner(t("status_judging"))
        self._analysis_worker = self.run_worker(
            self._run_analysis(),
            exclusive=True,
        )

    # -- helpers ---------------------------------------------------------------

    def _source_label(self) -> str:
        """Human-readable label for the current intent source."""
        return self._source_label_from(self._intent)

    @staticmethod
    def _source_label_from(intent: Intent) -> str:
        """Human-readable label from an intent."""
        if intent.type == "analyze_github":
            # Extract repo name from URL
            url = intent.url
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
            return url
        if intent.type == "analyze_web":
            url = intent.url
            # Strip protocol
            for prefix in ("https://", "http://"):
                if url.startswith(prefix):
                    url = url[len(prefix):]
            return url[:50]
        if intent.type == "analyze_file":
            return Path(intent.path).name
        if intent.type == "analyze_text":
            return (intent.text or intent.raw)[:40] + "..."
        if intent.type == "vote":
            return f"Vote: {', '.join(intent.providers)}"
        return intent.raw[:40]


def _short_path(path: Path) -> str:
    """Shorten path for footer display (~ for home)."""
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def _intent_to_input_type(intent: Intent) -> str:
    """Map intent type to input_type string for report widgets."""
    mapping = {
        "analyze_github": "github",
        "analyze_web": "web",
        "analyze_file": "local",
        "analyze_text": "local",
        "vote": "local",
    }
    return mapping.get(intent.type, "local")
