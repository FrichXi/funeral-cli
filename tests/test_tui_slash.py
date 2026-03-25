"""Tests for shared TUI slash-command routing."""

from __future__ import annotations

from funeralai.tui.intent import Intent
from funeralai.tui.slash import build_slash_intent, dispatch_standard_intent


class _FakeState:
    def __init__(self, can_vote: bool = True, providers: list[str] | None = None):
        self._can_vote = can_vote
        self._providers = providers or []

    def can_vote(self) -> bool:
        return self._can_vote

    def configured_providers(self) -> list[str]:
        return list(self._providers)


class _FakeApp:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def action_show_help(self) -> None:
        self.calls.append(("help",))

    def action_show_config(self) -> None:
        self.calls.append(("config",))

    def action_show_history(self) -> None:
        self.calls.append(("history",))

    def action_export_markdown(self) -> None:
        self.calls.append(("export",))

    def action_switch_theme(self) -> None:
        self.calls.append(("theme",))

    def action_switch_provider(self, provider: str = "") -> None:
        self.calls.append(("provider", provider))

    def action_switch_model(self, model: str = "") -> None:
        self.calls.append(("model", model))

    def action_switch_lang(self, lang: str = "") -> None:
        self.calls.append(("lang", lang))

    def start_analysis(self, intent: Intent) -> None:
        self.calls.append(("start_analysis", intent.raw, tuple(intent.providers)))


def test_build_slash_intent_vote_with_args():
    intent = build_slash_intent("/vote", "deepseek, openai")
    assert intent.type == "vote"
    assert intent.providers == ["deepseek", "openai"]


def test_build_slash_intent_vote_without_args():
    intent = build_slash_intent("/vote", "")
    assert intent.type == "vote"
    assert intent.providers == []


def test_build_slash_intent_vote_with_single_provider_keeps_provider():
    intent = build_slash_intent("/vote", "deepseek")
    assert intent.type == "vote"
    assert intent.providers == ["deepseek"]


def test_dispatch_standard_intent_routes_help_export_and_exit():
    app = _FakeApp()
    state = _FakeState()
    flags = {"exit": False, "clear": False}

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="help", raw="/help"),
        exit_action=lambda: flags.__setitem__("exit", True),
        clear_action=lambda: flags.__setitem__("clear", True),
    )
    assert ("help",) in app.calls

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="export_markdown", raw="/export"),
        exit_action=lambda: flags.__setitem__("exit", True),
        clear_action=lambda: flags.__setitem__("clear", True),
    )
    assert ("export",) in app.calls

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="exit", raw="/exit"),
        exit_action=lambda: flags.__setitem__("exit", True),
        clear_action=lambda: flags.__setitem__("clear", True),
    )
    assert flags["exit"] is True


def test_dispatch_standard_intent_clear_and_settings_actions():
    app = _FakeApp()
    state = _FakeState()
    flags = {"clear": False}

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="clear_screen", raw="/clear"),
        exit_action=lambda: None,
        clear_action=lambda: flags.__setitem__("clear", True),
    )
    assert flags["clear"] is True

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="switch_provider", raw="/provider deepseek", provider="deepseek"),
        exit_action=lambda: None,
        clear_action=lambda: None,
    )
    assert ("provider", "deepseek") in app.calls

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="switch_model", raw="/model gpt-4o", model="gpt-4o"),
        exit_action=lambda: None,
        clear_action=lambda: None,
    )
    assert ("model", "gpt-4o") in app.calls

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="switch_lang", raw="/lang zh", lang="zh"),
        exit_action=lambda: None,
        clear_action=lambda: None,
    )
    assert ("lang", "zh") in app.calls


def test_dispatch_standard_intent_vote_uses_explicit_or_configured_providers():
    app = _FakeApp()
    state = _FakeState(can_vote=True, providers=["deepseek", "openai"])
    messages: list[tuple[str, str]] = []

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="vote", raw="/vote deepseek openai", providers=["deepseek", "openai"]),
        exit_action=lambda: None,
        clear_action=lambda: None,
        status_action=lambda msg, style: messages.append((msg, style)),
    )
    assert ("start_analysis", "/vote deepseek openai", ("deepseek", "openai")) in app.calls

    app.calls.clear()
    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="vote", raw="/vote"),
        exit_action=lambda: None,
        clear_action=lambda: None,
        status_action=lambda msg, style: messages.append((msg, style)),
    )
    assert ("start_analysis", "/vote", ("deepseek", "openai")) in app.calls


def test_dispatch_standard_intent_vote_handles_missing_prior_analysis():
    app = _FakeApp()
    state = _FakeState(can_vote=False, providers=[])
    messages: list[tuple[str, str]] = []

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="vote", raw="/vote"),
        exit_action=lambda: None,
        clear_action=lambda: None,
        status_action=lambda msg, style: messages.append((msg, style)),
    )
    assert messages == [("  No previous analysis to vote on.", "dim")]


def test_dispatch_standard_intent_vote_warns_for_single_explicit_provider():
    app = _FakeApp()
    state = _FakeState(can_vote=True, providers=["deepseek", "openai"])
    messages: list[tuple[str, str]] = []

    assert dispatch_standard_intent(
        app,
        state,
        Intent(type="vote", raw="/vote deepseek", providers=["deepseek"]),
        exit_action=lambda: None,
        clear_action=lambda: None,
        status_action=lambda msg, style: messages.append((msg, style)),
    )
    assert app.calls == []
    assert messages == [("  Need >= 2 providers for vote.", "bold red")]
