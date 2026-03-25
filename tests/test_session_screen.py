"""Tests for SessionScreen in-place analysis flows."""

from __future__ import annotations

import asyncio

from textual.app import App

import funeralai.tui.screens.session as session_module
from funeralai.recommendations import RECOMMENDATION_NEUTRAL, RECOMMENDATION_POSITIVE
from funeralai.tui.intent import Intent
from funeralai.tui.screens.session import SessionScreen
from funeralai.tui.state import AppState
from funeralai.tui.widgets.prompt_input import PromptInput
from funeralai.tui.widgets.report import ReportView, VoteReportView


def _sample_result(recommendation: str = RECOMMENDATION_POSITIVE) -> dict:
    return {
        "primary_product": "Tabbit",
        "article_type": "evaluable",
        "investment_recommendation": recommendation,
        "product_reality": "一个主打标签智能分组和网页对话的 AI 浏览器。",
        "verdict": "产品定位有特色，但材料本身缺乏独立验证。",
        "information_completeness": "low",
        "advertorial_confidence": "high",
        "advertorial_signals": ["大段转述官方口径"],
        "evidence": [
            {
                "type": "risk",
                "claim": "文章内容主要来自团队自述，缺乏第三方验证。",
                "quote": "带着这些疑问声，我们深入挖掘了 Tabbit 背后的产品设计思路",
            },
        ],
    }


def _sample_vote_result() -> dict:
    return {
        "consensus": {
            "agreement": "majority",
            "recommendation": RECOMMENDATION_POSITIVE,
            "details": "两票正面，一票信息不足。",
        },
        "individual_results": [
            {"provider": "deepseek", "result": _sample_result(RECOMMENDATION_POSITIVE)},
            {"provider": "openai", "result": _sample_result(RECOMMENDATION_NEUTRAL)},
        ],
    }


class _SessionTestApp(App):
    CSS = ""

    def __init__(self, state: AppState, intent: Intent) -> None:
        super().__init__()
        self.state = state
        self._intent = intent
        self.start_analysis_calls: list[Intent] = []

    def on_mount(self) -> None:
        self.push_screen(SessionScreen(intent=self._intent, state=self.state))

    def start_analysis(self, intent: Intent) -> None:
        self.start_analysis_calls.append(intent)

    def action_show_help(self) -> None:
        pass

    def action_show_config(self) -> None:
        pass

    def action_show_history(self) -> None:
        pass

    def action_export_markdown(self) -> None:
        pass

    def action_switch_theme(self) -> None:
        pass

    def action_switch_provider(self, provider: str = "") -> None:
        pass

    def action_switch_model(self, model: str = "") -> None:
        pass

    def action_switch_lang(self, lang: str = "") -> None:
        pass


async def _wait_until_prompt_enabled(app: _SessionTestApp, pilot, max_ticks: int = 20) -> PromptInput:
    prompt: PromptInput | None = None
    for _ in range(max_ticks):
        await pilot.pause()
        prompt = app.screen.query_one(PromptInput)
        if not prompt.disabled:
            return prompt
    raise AssertionError("PromptInput did not become enabled in time")


def test_session_slash_vote_runs_in_place_and_preserves_history(monkeypatch):
    async def fake_dispatch_text(text: str, state: AppState) -> dict:
        state.reset_analysis()
        state.last_text = text
        state.last_input = text[:80]
        state.last_input_type = "text"
        state.last_prompt_version = 1
        state.last_inspection = None
        result = _sample_result()
        state.record_analysis(result)
        return result

    async def fake_dispatch_vote(
        providers: list[str],
        state: AppState,
        text: str | None = None,
    ) -> dict:
        assert providers == ["deepseek", "openai"]
        assert text is None
        result = _sample_vote_result()
        state.record_analysis(result)
        return result

    monkeypatch.setattr(session_module, "dispatch_text", fake_dispatch_text)
    monkeypatch.setattr(session_module, "dispatch_vote", fake_dispatch_vote)

    async def scenario() -> None:
        state = AppState(provider="deepseek", api_key="sk-test")
        app = _SessionTestApp(
            state,
            Intent(type="analyze_text", raw="initial text", text="initial text"),
        )

        async with app.run_test() as pilot:
            await _wait_until_prompt_enabled(app, pilot)

            screen = app.screen
            assert isinstance(screen, SessionScreen)
            before_children = len(screen.query_one("#session-scroll").children)
            assert len(list(screen.query(ReportView))) == 1
            assert len(list(screen.query(VoteReportView))) == 0

            for ch in "/vote deepseek,openai":
                await pilot.press(ch)
            await pilot.press("enter")

            await _wait_until_prompt_enabled(app, pilot)

            assert app.start_analysis_calls == []
            assert app.screen is screen
            assert len(list(screen.query(ReportView))) == 1
            assert len(list(screen.query(VoteReportView))) == 1
            assert len(screen.query_one("#session-scroll").children) > before_children

    asyncio.run(scenario())


def test_cancel_analysis_restores_prompt(monkeypatch):
    async def slow_dispatch_text(text: str, state: AppState) -> dict:
        await asyncio.sleep(10)
        raise AssertionError("cancel should stop this worker first")

    monkeypatch.setattr(session_module, "dispatch_text", slow_dispatch_text)

    async def scenario() -> None:
        state = AppState(provider="deepseek", api_key="sk-test")
        app = _SessionTestApp(
            state,
            Intent(type="analyze_text", raw="slow text", text="slow text"),
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SessionScreen)
            prompt = screen.query_one(PromptInput)
            assert prompt.disabled is True

            screen.action_cancel_analysis()
            prompt = await _wait_until_prompt_enabled(app, pilot)

            assert prompt.disabled is False
            status_lines = [widget._msg_text for widget in screen.query(session_module.StatusMessage)]
            assert any("已取消当前任务" in line or "cancelled" in line.lower() for line in status_lines)

    asyncio.run(scenario())
