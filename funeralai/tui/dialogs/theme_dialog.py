"""Theme selection dialog."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, OptionList
from textual.widgets.option_list import Option
from rich.text import Text

from funeralai.tui.theme import (
    Theme,
    get_theme_from_config,
    save_theme_to_config,
)


class ThemeDialog(ModalScreen[str | None]):
    """Modal dialog for switching themes."""

    DEFAULT_CSS = """
    ThemeDialog {
        align: center middle;
    }

    #theme-dialog-box {
        width: 50;
        max-height: 20;
        border: round $accent;
        background: transparent;
        padding: 1 2;
    }

    #theme-dialog-box #theme-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #theme-dialog-box OptionList {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }

    #theme-btn-row {
        height: 3;
        align: center middle;
    }

    #theme-btn-row Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current = get_theme_from_config()
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-dialog-box"):
            yield Static("Switch Theme", id="theme-title")
            yield OptionList(*self._build_options(), id="theme-list")
            with Horizontal(id="theme-btn-row"):
                yield Button("Apply", variant="primary", id="btn-apply")
                yield Button("Cancel", id="btn-cancel")

    def _build_options(self) -> list[Option]:
        available = Theme.available_themes()
        options = []
        mode = getattr(getattr(self.app, "theme_obj", None), "mode", "dark")
        for name in available:
            theme = Theme(name, mode)
            swatch = f"[{theme.colors.primary}]|||[/]"
            marker = " [bold]<[/]" if name == self._current else ""
            label = Text.from_markup(f" {swatch}  {name}{marker}")
            options.append(Option(label, id=name))
        return options

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option.id:
            self._selected = event.option.id

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id:
            self._selected = event.option.id
            self._apply()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apply":
            self._apply()
        else:
            self.dismiss(None)

    def _apply(self) -> None:
        if self._selected:
            save_theme_to_config(self._selected)
            self.dismiss(self._selected)

    def action_cancel(self) -> None:
        self.dismiss(None)
