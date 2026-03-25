"""Help dialog showing keyboard shortcuts and command reference."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_TEXT = """\
[bold]Keyboard Shortcuts[/]

  [cyan]Enter[/]        Submit input
  [cyan]Ctrl+P[/]       Command palette
  [cyan]Ctrl+Q[/]       Exit
  [cyan]Escape[/]       Close dialog / cancel

[bold]Input Types[/]

  [green]GitHub URL[/]    https://github.com/owner/repo
  [green]Web URL[/]       https://example.com
  [green]File path[/]     /path/to/article.md
  [green]Directory[/]     /path/to/dir/ (batch)
  [green]Long text[/]     Paste >300 chars to analyze

[bold]Slash Commands[/]

  /provider     Switch provider
  /model        Switch model
  /vote         Multi-model vote
  /export       Export current report as Markdown
  /lang zh|en   Switch UI language
  /theme        Switch theme
  /config       Show configuration
  /history      Analysis history
  /clear        Clear screen
  /help         This dialog

[bold]Natural Language[/]

  用 deepseek       Switch provider
  投票 a,b,c        Multi-model vote
  再来一次          Retry last analysis

[dim]Press Escape to close[/]\
"""


class HelpDialog(ModalScreen[None]):
    """Modal help screen with keyboard shortcuts and commands."""

    DEFAULT_CSS = """
    HelpDialog {
        align: center middle;
    }

    #help-dialog-box {
        width: 58;
        max-height: 36;
        border: round $accent;
        background: transparent;
        padding: 1 2;
        overflow-y: auto;
    }

    #help-dialog-box #help-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_help", "Close"),
        ("q", "dismiss_help", "Close"),
        ("?", "dismiss_help", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog-box"):
            yield Static("Help", id="help-title")
            yield Static(_HELP_TEXT, id="help-content")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)
