"""Core input widget with autocomplete — maps to OpenCode's prompt component.

Contains PromptInput (the main widget), AutocompleteDropdown, PromptHistory,
and custom messages (PromptSubmitted, SlashCommand) that bubble up to screens.
"""

from __future__ import annotations

import glob as _glob_mod
import os
import random
from difflib import SequenceMatcher
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static

from funeralai.i18n import PLACEHOLDER_KEYS, t

# ---------------------------------------------------------------------------
# Custom messages
# ---------------------------------------------------------------------------


class PromptSubmitted(Message):
    """Posted when the user presses Enter in the prompt."""

    def __init__(self, value: str) -> None:
        super().__init__()
        self.value = value


class SlashCommand(Message):
    """Posted when a slash command is selected (autocomplete or typed)."""

    def __init__(self, command: str, arg: str = "") -> None:
        super().__init__()
        self.command = command
        self.arg = arg


# ---------------------------------------------------------------------------
# Prompt history (persistent, file-based)
# ---------------------------------------------------------------------------

_HISTORY_PATH = Path.home() / ".config" / "funeralai" / "history"
_MAX_HISTORY = 500


class PromptHistory:
    """Load / save prompt history from ~/.config/funeralai/history."""

    def __init__(self) -> None:
        self._entries: list[str] = []
        self._pos: int = -1  # -1 means "not browsing"
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        try:
            text = _HISTORY_PATH.read_text(encoding="utf-8")
            self._entries = [
                line for line in text.splitlines() if line.strip()
            ][-_MAX_HISTORY:]
        except Exception:
            self._entries = []

    def _save(self) -> None:
        try:
            _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            _HISTORY_PATH.write_text(
                "\n".join(self._entries[-_MAX_HISTORY:]) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    # -- public API ----------------------------------------------------------

    def add(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        # Deduplicate last entry
        if self._entries and self._entries[-1] == text:
            return
        self._entries.append(text)
        self._entries = self._entries[-_MAX_HISTORY:]
        self._save()

    def get_prev(self) -> str | None:
        """Move backward through history. Returns entry or None."""
        if not self._entries:
            return None
        if self._pos == -1:
            self._pos = len(self._entries) - 1
        elif self._pos > 0:
            self._pos -= 1
        return self._entries[self._pos]

    def get_next(self) -> str | None:
        """Move forward through history. Returns entry or None (end)."""
        if self._pos == -1:
            return None
        if self._pos < len(self._entries) - 1:
            self._pos += 1
            return self._entries[self._pos]
        # Past the end -> exit history browsing
        self._pos = -1
        return None

    def reset_position(self) -> None:
        self._pos = -1


# ---------------------------------------------------------------------------
# Slash commands definition
# ---------------------------------------------------------------------------

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show help"),
    ("/provider", "Switch provider"),
    ("/model", "Switch model"),
    ("/vote", "Multi-model vote"),
    ("/export", "Export report as Markdown"),
    ("/lang", "Switch language"),
    ("/history", "Show history"),
    ("/config", "Show config"),
    ("/theme", "Switch theme"),
    ("/clear", "Clear screen"),
    ("/exit", "Exit"),
]

# ---------------------------------------------------------------------------
# Autocomplete dropdown
# ---------------------------------------------------------------------------

_MAX_VISIBLE = 8


class AutocompleteDropdown(Widget):
    """Dropdown list for slash-command and file-path autocomplete."""

    DEFAULT_CSS = """
    AutocompleteDropdown {
        layer: overlay;
        dock: bottom;
        width: 100%;
        max-height: 12;
        display: none;
        background: $surface;
        border: solid $accent;
    }
    AutocompleteDropdown .ac-item {
        padding: 0 1;
        height: 1;
    }
    AutocompleteDropdown .ac-item.--selected {
        background: $accent 30%;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._items: list[tuple[str, str]] = []  # (value, description)
        self._selected: int = 0
        self._mode: str = "command"  # "command" or "file"

    # -- rendering -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Vertical()  # items rendered dynamically inside this container

    def _render_items(self) -> None:
        """Re-render visible item list."""
        container = self.query_one(Vertical)
        container.remove_children()

        visible = self._visible_slice()
        for i, (val, desc) in enumerate(visible):
            label = f"  {val}  {desc}" if desc else f"  {val}"
            item = Static(label, classes="ac-item")
            if i == self._selected - self._scroll_offset():
                item.add_class("--selected")
            container.mount(item)

    def _visible_slice(self) -> list[tuple[str, str]]:
        offset = self._scroll_offset()
        return self._items[offset : offset + self._visible_capacity()]

    def _visible_capacity(self) -> int:
        """Return how many rows are actually visible inside the dropdown.

        The overlay may have less vertical room than `_MAX_VISIBLE`, especially
        near the bottom of small terminals. Scrolling must follow the rendered
        height instead of assuming all configured rows are visible.
        """
        height = self.size.height
        if height <= 0:
            return _MAX_VISIBLE
        content_rows = max(1, height - 2)  # account for the border
        return min(_MAX_VISIBLE, content_rows, max(1, len(self._items)))

    def _scroll_offset(self) -> int:
        capacity = self._visible_capacity()
        if self._selected < capacity:
            return 0
        return self._selected - capacity + 1

    # -- public API ----------------------------------------------------------

    def show_commands(self, query: str) -> None:
        """Filter slash commands by query and display."""
        self._mode = "command"
        q = query.lstrip("/").strip().lower()
        if not q:
            self._items = list(SLASH_COMMANDS)
        else:
            ranked: list[tuple[tuple[int, float, int, str], tuple[str, str]]] = []
            for order, (cmd, desc) in enumerate(SLASH_COMMANDS):
                rank = _rank_slash_command(q, cmd, order)
                if rank is not None:
                    ranked.append((rank, (cmd, desc)))
            ranked.sort(key=lambda item: item[0])
            self._items = [item for _, item in ranked]
        self._selected = 0
        self._update_visibility()

    def show_files(self, query: str) -> None:
        """Glob current directory for files matching query.

        Uses iglob with itertools.islice to cap results at 20 entries,
        avoiding a full directory enumeration that would block the event loop.
        """
        self._mode = "file"
        _MAX_FILE_RESULTS = 20
        try:
            pattern = f"*{query}*" if query else "*"
            matches = _glob_mod.iglob(pattern)
            # Filter hidden files on the fly and stop after _MAX_FILE_RESULTS
            results: list[str] = []
            for p in matches:
                if not os.path.basename(p).startswith("."):
                    results.append(p)
                    if len(results) >= _MAX_FILE_RESULTS:
                        break
            self._items = [(p, "") for p in sorted(results)]
        except Exception:
            self._items = []
        self._selected = 0
        self._update_visibility()

    def hide(self) -> None:
        self.display = False
        self._items = []

    def move_up(self) -> None:
        if self._items and self._selected > 0:
            self._selected -= 1
            self._render_items()

    def move_down(self) -> None:
        if self._items and self._selected < len(self._items) - 1:
            self._selected += 1
            self._render_items()

    def get_selected(self) -> str | None:
        """Return the value of the currently selected item."""
        if 0 <= self._selected < len(self._items):
            return self._items[self._selected][0]
        return None

    @property
    def selected_index(self) -> int:
        return self._selected

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_visible(self) -> bool:
        return bool(self.display) and bool(self._items)

    def _update_visibility(self) -> None:
        if self._items:
            self.display = True
            self._render_items()
        else:
            self.display = False


# ---------------------------------------------------------------------------
# Fuzzy matching helper
# ---------------------------------------------------------------------------


def _fuzzy_match(query: str, candidate: str, threshold: float = 0.3) -> bool:
    """Return True if query fuzzy-matches candidate."""
    if query in candidate:
        return True
    return SequenceMatcher(None, query, candidate).ratio() > threshold


def _rank_slash_command(
    query: str,
    candidate: str,
    order: int,
) -> tuple[int, float, int, str] | None:
    """Rank a slash-command candidate for autocomplete."""
    q = query.strip().lower()
    c = candidate.lstrip("/").lower()
    if not q:
        return (3, 0.0, order, c)
    if q == c:
        return (0, 0.0, order, c)
    if c.startswith(q):
        return (1, 0.0, order, c)
    score = SequenceMatcher(None, q, c).ratio()
    if score > 0.3:
        return (2, -score, order, c)
    return None


# ---------------------------------------------------------------------------
# Main prompt input widget
# ---------------------------------------------------------------------------


class PromptInput(Widget):
    """Prompt input bar with history and autocomplete.

    Posts ``PromptSubmitted`` when the user hits Enter.
    Posts ``SlashCommand`` when a slash command is selected.
    """

    DEFAULT_CSS = """
    PromptInput {
        height: auto;
        dock: bottom;
        padding: 0 0;
    }
    PromptInput .prompt-line {
        width: 100%;
        height: 1;
        color: $text-muted;
    }
    PromptInput .prompt-row {
        height: auto;
        layout: horizontal;
        padding: 0 1;
    }
    PromptInput .prompt-char {
        width: 2;
        height: 1;
        color: $accent;
        text-style: bold;
        padding: 0 0;
    }
    PromptInput Input {
        width: 1fr;
        border: none;
    }
    PromptInput Input:focus {
        border: none;
    }
    PromptInput Input.-disabled {
        opacity: 0.4;
    }
    PromptInput .prompt-char.-disabled {
        opacity: 0.4;
    }
    """

    disabled = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self._history = PromptHistory()
        self._default_placeholder = t(random.choice(PLACEHOLDER_KEYS))
        self._disabled_reason = ""

    def compose(self) -> ComposeResult:
        yield AutocompleteDropdown()
        yield Static("─" * 200, classes="prompt-line")
        with Horizontal(classes="prompt-row"):
            yield Static("❯ ", classes="prompt-char")
            yield Input(placeholder=self._default_placeholder)
        yield Static("─" * 200, classes="prompt-line")

    # -- event handlers ------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show / hide autocomplete based on input text."""
        text = event.value
        dropdown = self.query_one(AutocompleteDropdown)

        if text.startswith("/"):
            command_tail = text[1:]
            if command_tail and any(ch.isspace() for ch in command_tail):
                dropdown.hide()
            else:
                dropdown.show_commands(text)
        elif "@" in text:
            # File autocomplete: extract query after last @
            at_idx = text.rfind("@")
            file_query = text[at_idx + 1 :]
            dropdown.show_files(file_query)
        else:
            dropdown.hide()

    def on_key(self, event) -> None:
        """Handle special keys: Enter, Up, Down, Escape, Tab."""
        inp = self.query_one(Input)
        dropdown = self.query_one(AutocompleteDropdown)

        if event.key == "enter":
            event.prevent_default()
            text = self._command_text_for_enter(inp.value.strip(), dropdown)
            if text:
                self._history.add(text)
                self._history.reset_position()
                # Check if it's a slash command
                if text.startswith("/"):
                    parts = text.split(None, 1)
                    cmd = parts[0]
                    arg = parts[1] if len(parts) > 1 else ""
                    self.post_message(SlashCommand(cmd, arg))
                else:
                    self.post_message(PromptSubmitted(text))
                inp.value = ""
                dropdown.hide()
            return

        if event.key == "escape":
            if dropdown.is_visible:
                event.prevent_default()
                dropdown.hide()
                self._focus_input()
            return

        if event.key == "up":
            if dropdown.is_visible:
                event.prevent_default()
                dropdown.move_up()
            else:
                event.prevent_default()
                prev = self._history.get_prev()
                if prev is not None:
                    inp.value = prev
                    inp.cursor_position = len(prev)
            return

        if event.key == "down":
            if dropdown.is_visible:
                event.prevent_default()
                dropdown.move_down()
            else:
                event.prevent_default()
                nxt = self._history.get_next()
                inp.value = nxt if nxt is not None else ""
                inp.cursor_position = len(inp.value)
            return

        if event.key == "tab":
            if dropdown.is_visible:
                event.prevent_default()
                selected = dropdown.get_selected()
                if selected:
                    self._accept_autocomplete(selected)
                    dropdown.hide()
                    self._focus_input()
            return

    def _accept_autocomplete(self, value: str) -> None:
        """Insert selected autocomplete value into input."""
        inp = self.query_one(Input)
        text = inp.value

        if self.query_one(AutocompleteDropdown)._mode == "file":
            # Replace the @query portion
            at_idx = text.rfind("@")
            if at_idx >= 0:
                inp.value = text[:at_idx] + value
            else:
                inp.value = value
        else:
            # Slash command: replace entire input, add trailing space
            inp.value = value + " "
        inp.cursor_position = len(inp.value)

    def _command_text_for_enter(
        self,
        text: str,
        dropdown: AutocompleteDropdown,
    ) -> str:
        """Resolve the submitted text for Enter presses.

        When the slash-command dropdown is open and the user has typed a
        partial command, pressing Enter should execute the highlighted command
        instead of submitting the incomplete prefix as an unknown command.
        """
        if (
            not dropdown.is_visible
            or dropdown.mode != "command"
            or not text.startswith("/")
        ):
            return text

        selected = dropdown.get_selected()
        command_tail = text[1:]
        if not command_tail:
            if dropdown.selected_index > 0 and selected:
                return selected
            return text
        if any(ch.isspace() for ch in command_tail):
            return text

        return selected or text

    def _focus_input(self) -> None:
        """Return focus to the input widget."""
        try:
            self.query_one(Input).focus(scroll_visible=False)
        except Exception:
            pass

    # -- public API ----------------------------------------------------------

    def focus(self, scroll_visible: bool = True) -> None:
        """Delegate focus to the inner Input widget."""
        try:
            self.query_one(Input).focus(scroll_visible=scroll_visible)
        except Exception:
            pass

    def set_disabled_reason(self, reason: str | None) -> None:
        """Set a visible reason shown in the input placeholder when disabled."""
        self._disabled_reason = (reason or "").strip()
        self._update_placeholder()

    def _update_placeholder(self) -> None:
        """Refresh the inner input placeholder for enabled / disabled states."""
        try:
            inp = self.query_one(Input)
            if self.disabled and self._disabled_reason:
                inp.placeholder = self._disabled_reason
            else:
                inp.placeholder = self._default_placeholder
        except Exception:
            pass

    def watch_disabled(self, value: bool) -> None:
        """Toggle disabled styling on the inner Input and prompt char."""
        try:
            inp = self.query_one(Input)
            inp.disabled = value
            if value:
                inp.add_class("-disabled")
            else:
                inp.remove_class("-disabled")
        except Exception:
            pass
        try:
            char = self.query_one(".prompt-char", Static)
            if value:
                char.add_class("-disabled")
            else:
                char.remove_class("-disabled")
        except Exception:
            pass
        try:
            dropdown = self.query_one(AutocompleteDropdown)
            if value:
                dropdown.hide()
        except Exception:
            pass
        self._update_placeholder()
