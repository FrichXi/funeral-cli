"""Tests for output formatting and Markdown export helpers."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console

from funeralai.exporting import default_export_path, render_markdown
from funeralai.output import (
    _display_width,
    format_json,
    format_markdown,
    render_report,
)
from funeralai.recommendations import (
    RECOMMENDATION_NEGATIVE,
    RECOMMENDATION_NEUTRAL,
    RECOMMENDATION_POSITIVE,
)


def _sample_result(recommendation: str = RECOMMENDATION_POSITIVE) -> dict:
    return {
        "primary_product": "Tabbit",
        "article_type": "evaluable",
        "investment_recommendation": recommendation,
        "product_reality": "一个主打标签智能分组和网页对话的 AI 浏览器。",
        "verdict": "产品定位有特色，但报道材料本身缺乏独立验证。",
        "information_completeness": "low",
        "advertorial_confidence": "high",
        "advertorial_signals": ["大段转述官方口径", "缺少负面体验展开"],
        "evidence": [
            {
                "type": "risk",
                "claim": "文章内容主要来自团队自述，缺乏第三方验证和独立测试。",
                "quote": "带着这些疑问声，我们深入挖掘了 Tabbit 背后的产品设计思路",
            },
            {
                "type": "fact",
                "claim": "文章明确提到当前不支持 Python 等代码脚本执行。",
                "quote": "Kimi 作为独立工具，支持执行 Python 等代码脚本，而Tabbit 目前不支持",
            },
        ],
    }


def test_markdown_uses_canonical_recommendation_labels():
    text = format_markdown(_sample_result("牛逼"))
    assert "## 投资建议" in text
    assert "🤓 整挺好" in text
    assert "值得进一步看" not in text
    assert "牛逼" not in text


def test_markdown_supports_neutral_label():
    text = format_markdown(_sample_result(RECOMMENDATION_NEUTRAL))
    assert "🤔 整不明白" in text


def test_json_normalizes_legacy_recommendation_labels():
    payload = format_json(_sample_result("傻逼"))
    assert RECOMMENDATION_NEGATIVE in payload
    assert "暂不建议投资" not in payload
    assert '"傻逼"' not in payload
    assert '"吹牛逼"' not in payload


def test_render_report_wraps_narrow_cjk_content():
    console = Console(width=36, record=True, force_terminal=False, color_system=None)
    console.print(render_report(_sample_result()))
    rendered = console.export_text()

    assert rendered
    assert all(_display_width(line) <= 36 for line in rendered.splitlines())


def test_markdown_uses_summary_sections_before_evidence():
    text = format_markdown(_sample_result())

    assert "## 判断" in text
    assert "## 投资建议" in text
    assert "## 产品实况" in text
    assert "## 关键证据" in text
    assert "## 信息完整度" in text
    assert text.index("## 判断") < text.index("## 投资建议") < text.index("## 产品实况") < text.index("## 关键证据")
    assert "| # | 证据 | 原文/数据 | 类型 |" in text


def test_render_report_shows_judgment_before_evidence():
    console = Console(width=80, record=True, force_terminal=False, color_system=None)
    console.print(render_report(_sample_result()))
    rendered = console.export_text()

    assert "判断" in rendered
    assert "投资建议" in rendered
    assert "产品实况" in rendered
    assert "关键证据" in rendered
    assert rendered.index("判断") < rendered.index("关键证据")


def test_render_markdown_handles_vote_results():
    vote_result = {
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

    text = render_markdown(vote_result)
    assert "多模型投票" in text
    assert "deepseek" in text
    assert "openai" in text


def test_default_export_path_uses_timestamp_and_slug(tmp_path):
    path = default_export_path(
        _sample_result(),
        base_dir=tmp_path,
        now=datetime(2026, 3, 25, 10, 11),
    )
    assert path.parent == tmp_path
    assert path.name == "2026-03-25_1011_Tabbit.md"
