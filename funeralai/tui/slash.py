"""Shared slash-command routing for Home and Session screens."""

from __future__ import annotations

import re
from collections.abc import Callable

from funeralai.tui.intent import Intent, parse_intent


def build_slash_intent(command: str, arg: str = "") -> Intent:
    """Build an Intent from a slash command event."""
    cmd = command.lstrip("/").lower()
    full = f"{command} {arg}".strip() if arg else command

    if cmd == "vote":
        providers = [
            name.strip().lower()
            for name in re.split(r"[,\s]+", arg)
            if name.strip()
        ]
        return Intent(type="vote", raw=full, providers=providers)

    return parse_intent(full)


def dispatch_standard_intent(
    app,
    state,
    intent: Intent,
    *,
    exit_action: Callable[[], None],
    clear_action: Callable[[], None],
    status_action: Callable[[str, str], None] | None = None,
    start_vote_action: Callable[[Intent], None] | None = None,
) -> bool:
    """Dispatch shared command intents.

    Returns True when the intent has been handled.
    """
    if intent.type == "exit":
        exit_action()
        return True

    if intent.type == "help":
        app.action_show_help()
        return True

    if intent.type == "clear_screen":
        clear_action()
        return True

    if intent.type == "show_config":
        app.action_show_config()
        return True

    if intent.type == "show_history":
        app.action_show_history()
        return True

    if intent.type == "export_markdown":
        app.action_export_markdown()
        return True

    if intent.type == "switch_theme":
        app.action_switch_theme()
        return True

    if intent.type == "switch_provider":
        app.action_switch_provider(intent.provider)
        return True

    if intent.type == "switch_model":
        app.action_switch_model(intent.model)
        return True

    if intent.type == "switch_lang":
        app.action_switch_lang(intent.lang)
        return True

    if intent.type == "vote":
        return _dispatch_vote(
            app,
            state,
            intent,
            status_action=status_action,
            start_vote_action=start_vote_action,
        )

    return False


def _dispatch_vote(
    app,
    state,
    intent: Intent,
    *,
    status_action: Callable[[str, str], None] | None,
    start_vote_action: Callable[[Intent], None] | None,
) -> bool:
    providers = list(intent.providers)
    if providers:
        if len(providers) >= 2:
            _start_vote(
                app,
                intent,
                providers,
                start_vote_action=start_vote_action,
            )
        elif status_action:
            status_action(
                "  Need >= 2 providers for vote.",
                "bold red",
            )
        return True

    if state.can_vote():
        providers = state.configured_providers()
        if len(providers) >= 2:
            _start_vote(
                app,
                intent,
                providers,
                start_vote_action=start_vote_action,
            )
        elif status_action:
            status_action(
                "  Need >= 2 configured providers for vote.",
                "bold red",
            )
        return True

    if status_action:
        status_action("  No previous analysis to vote on.", "dim")
    return True


def _start_vote(
    app,
    intent: Intent,
    providers: list[str],
    *,
    start_vote_action: Callable[[Intent], None] | None,
) -> None:
    vote_intent = Intent(
        type="vote",
        raw=intent.raw or "/vote",
        providers=providers,
    )
    if start_vote_action is not None:
        start_vote_action(vote_intent)
    else:
        app.start_analysis(vote_intent)
