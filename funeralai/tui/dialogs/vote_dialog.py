"""Multi-model vote selection dialog.

Shows checkboxes for all configured providers. User selects 2+ to vote.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, SelectionList
from textual.widgets.selection_list import Selection

from funeralai.analyzer import PROVIDERS
from funeralai.config import get_api_key


class VoteDialog(ModalScreen[list[str] | None]):
    """Modal dialog for selecting providers for multi-model vote."""

    DEFAULT_CSS = """
    VoteDialog {
        align: center middle;
    }

    #vote-dialog-box {
        width: 55;
        max-height: 22;
        border: round $accent;
        background: transparent;
        padding: 1 2;
    }

    #vote-dialog-box #title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #vote-dialog-box #hint {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #vote-dialog-box SelectionList {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }

    #vote-btn-row {
        height: 3;
        align: center middle;
    }

    #vote-btn-row Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="vote-dialog-box"):
            yield Static("Multi-model Vote", id="title")
            yield Static("Select 2+ providers", id="hint")
            yield SelectionList[str](
                *self._build_selections(),
                id="vote-list",
            )
            with Horizontal(id="vote-btn-row"):
                yield Button("Vote", variant="primary", id="btn-vote")
                yield Button("Cancel", id="btn-cancel")

    def _build_selections(self) -> list[Selection[str]]:
        selections = []
        for name in PROVIDERS:
            key = get_api_key(name)
            if key:
                model = PROVIDERS[name]["default_model"]
                label = f"{name} ({model})"
                selections.append(Selection(label, name))
        return selections

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-vote":
            self._try_vote()
        else:
            self.dismiss(None)

    def _try_vote(self) -> None:
        selection_list = self.query_one("#vote-list", SelectionList)
        selected = list(selection_list.selected)
        if len(selected) < 2:
            hint = self.query_one("#hint", Static)
            hint.update("[red]Select at least 2 providers[/]")
            return
        self.dismiss(selected)

    def action_cancel(self) -> None:
        self.dismiss(None)
