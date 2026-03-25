"""Tests for the PromptInput widget behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input

import funeralai.tui.widgets.prompt_input as prompt_input_module
from funeralai.tui.widgets.prompt_input import (
    AutocompleteDropdown,
    PromptInput,
    PromptSubmitted,
    SlashCommand,
)


class _PromptTestApp(App):
    CSS = ""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple] = []

    def compose(self) -> ComposeResult:
        yield PromptInput()

    def on_mount(self) -> None:
        self.query_one(PromptInput).focus()

    def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        self.events.append(("prompt", event.value))

    def on_slash_command(self, event: SlashCommand) -> None:
        self.events.append(("slash", event.command, event.arg))


def _write_history(path: Path, *entries: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")


def _run_prompt_scenario(coro):
    asyncio.run(coro)


def test_exact_slash_command_executes_on_single_enter(tmp_path, monkeypatch):
    history_path = tmp_path / "history"
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            inp = app.query_one(Input)
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            for ch in "export":
                await pilot.press(ch)
            await pilot.pause()

            assert dropdown.is_visible
            assert dropdown.get_selected() == "/export"

            await pilot.press("enter")
            await pilot.pause()

            assert app.events == [("slash", "/export", "")]
            assert inp.value == ""
            assert not dropdown.is_visible

    _run_prompt_scenario(scenario())


def test_partial_slash_command_executes_selected_on_enter(tmp_path, monkeypatch):
    history_path = tmp_path / "history"
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            inp = app.query_one(Input)
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            for ch in "ex":
                await pilot.press(ch)
            await pilot.pause()

            assert dropdown.is_visible
            assert dropdown.get_selected() == "/export"

            await pilot.press("enter")
            await pilot.pause()

            assert app.events == [("slash", "/export", "")]
            assert inp.value == ""
            assert not dropdown.is_visible

    _run_prompt_scenario(scenario())


def test_tab_accepts_autocomplete_without_executing(tmp_path, monkeypatch):
    history_path = tmp_path / "history"
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            inp = app.query_one(Input)
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            for ch in "ex":
                await pilot.press(ch)
            await pilot.pause()

            assert dropdown.is_visible
            assert dropdown.get_selected() == "/export"

            await pilot.press("tab")
            await pilot.pause()

            assert inp.value == "/export "
            assert inp.cursor_position == len(inp.value)
            assert app.events == []
            assert not dropdown.is_visible

    _run_prompt_scenario(scenario())


def test_down_navigation_and_enter_execute_selected_command(tmp_path, monkeypatch):
    history_path = tmp_path / "history"
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            await pilot.pause()

            for _ in range(4):
                await pilot.press("down")
            await pilot.pause()

            assert dropdown.get_selected() == "/export"

            await pilot.press("enter")
            await pilot.pause()

            assert app.events == [("slash", "/export", "")]

    _run_prompt_scenario(scenario())


def test_escape_closes_dropdown_without_clearing_input_or_focus(
    tmp_path, monkeypatch
):
    history_path = tmp_path / "history"
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            inp = app.query_one(Input)
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            for ch in "ex":
                await pilot.press(ch)
            await pilot.pause()

            assert dropdown.is_visible

            await pilot.press("escape")
            await pilot.pause()

            assert inp.value == "/ex"
            assert inp.has_focus
            assert not dropdown.is_visible

    _run_prompt_scenario(scenario())


def test_dropdown_scroll_offset_tracks_visible_capacity():
    dropdown = AutocompleteDropdown()
    dropdown._items = [(f"/cmd{i}", "") for i in range(6)]
    dropdown._selected = 4
    dropdown._visible_capacity = lambda: 3

    assert dropdown._scroll_offset() == 2
    assert dropdown._visible_slice() == [
        ("/cmd2", ""),
        ("/cmd3", ""),
        ("/cmd4", ""),
    ]


def test_up_down_use_dropdown_when_visible_and_history_when_hidden(
    tmp_path, monkeypatch
):
    history_path = tmp_path / "history"
    _write_history(history_path, "first", "second")
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            inp = app.query_one(Input)
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            for ch in "ex":
                await pilot.press(ch)
            await pilot.pause()

            assert dropdown.is_visible
            first_selected = dropdown.get_selected()

            await pilot.press("down")
            await pilot.pause()

            assert dropdown.get_selected() != first_selected
            assert inp.value == "/ex"

            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("up")
            await pilot.pause()
            assert inp.value == "second"

            await pilot.press("down")
            await pilot.pause()
            assert inp.value == ""

    _run_prompt_scenario(scenario())


def test_disabled_prompt_hides_dropdown_and_shows_reason(tmp_path, monkeypatch):
    history_path = tmp_path / "history"
    monkeypatch.setattr(prompt_input_module, "_HISTORY_PATH", history_path)

    async def scenario() -> None:
        app = _PromptTestApp()
        async with app.run_test() as pilot:
            prompt = app.query_one(PromptInput)
            inp = app.query_one(Input)
            dropdown = app.query_one(AutocompleteDropdown)

            await pilot.press("/")
            for ch in "vo":
                await pilot.press(ch)
            await pilot.pause()

            assert dropdown.is_visible

            prompt.set_disabled_reason("Running vote... input paused")
            prompt.disabled = True
            await pilot.pause()

            assert not dropdown.is_visible
            assert inp.disabled is True
            assert inp.placeholder == "Running vote... input paused"

            prompt.disabled = False
            await pilot.pause()

            assert inp.disabled is False
            assert inp.placeholder != "Running vote... input paused"

    _run_prompt_scenario(scenario())
