"""Command palette provider for the Textual TUI.

Integrates with Textual's built-in CommandPalette (ctrl+p).
Each command fires a Textual action on the app for dispatch.
"""

from __future__ import annotations

import functools

from textual.command import Provider, Hits, Hit


# (display title, action string, optional keybind help)
_COMMANDS: list[tuple[str, str, str]] = [
    ("Switch Provider", "switch_provider", ""),
    ("Switch Model", "switch_model", ""),
    ("Multi-model Vote", "vote", ""),
    ("Export Markdown", "export_markdown", ""),
    ("Switch Language", "switch_lang", ""),
    ("Switch Theme", "switch_theme", ""),
    ("Show Config", "show_config", ""),
    ("Show Help", "show_help", "?"),
    ("New Analysis", "new_analysis", ""),
    ("History", "show_history", ""),
    ("Clear Screen", "clear_screen", ""),
    ("Retry Analysis", "retry_analysis", ""),
    ("Exit", "quit", "ctrl+q"),
]


class FuneralCommands(Provider):
    """Provides slash-command-like actions via the Textual command palette."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for title, action, keybind in _COMMANDS:
            score = matcher.match(title)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(title),
                    functools.partial(self._run_action, action),
                    help=keybind or None,
                )

    async def _run_action(self, action: str) -> None:
        """Fire the action on the app."""
        self.app.call_later(self.app.run_action, action)
