"""Output formatting for terminal, Markdown, JSON, and TUI renderables."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text

from funeralai.recommendations import (
    DEFAULT_RECOMMENDATION,
    normalize_recommendation,
    recommendation_bucket,
)


# Terminal colors (ANSI)
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"

_EVIDENCE_TYPE_ZH = {
    "fact": "事实",
    "inference": "推断",
    "risk": "风险",
    "promotional": "推广",
    "code_inspection": "代码实查",
    "product_testing": "产品实测",
}

_INFO_COMPLETENESS_COPY = {
    "high": "信息相对完整，材料已经覆盖产品形态、使用情况和关键验证点。",
    "medium": "信息不算完整，能看到部分产品和使用信号，但关键验证还不够扎实。",
    "low": "缺口很大，材料缺少能验证复用、留存、付费或任务闭环的硬证据，当前只能保守判断。",
}


def _use_color() -> bool:
    """Check if stdout supports color."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _make_c():
    """Return a colorize helper based on current terminal capability."""
    if _use_color():
        return lambda code, text: f"{code}{text}{_RESET}"
    return lambda code, text: text


def format_json(result: Any) -> str:
    """Format result as JSON string."""
    if isinstance(result, dict) and result.get("consensus"):
        payload = _normalized_vote_result(result)
    elif isinstance(result, dict) and "investment_recommendation" in result:
        payload = _normalized_result(result)
    elif isinstance(result, list):
        payload = [
            {**entry, "result": _normalized_result(entry["result"])}
            if isinstance(entry, dict) and "result" in entry and isinstance(entry["result"], dict)
            else entry
            for entry in result
        ]
    else:
        payload = result
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _type_label(article_type: str) -> str:
    """Human-readable label for article_type."""
    labels = {
        "evaluable": "可评估",
        "non_evaluable": "不涉及产品评价",
        "advertorial": "广告/软文",
    }
    return labels.get(article_type, article_type)


def _display_width(s: str) -> int:
    """Approximate display width accounting for CJK double-width characters."""
    w = 0
    for ch in s:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0xF900 <= cp <= 0xFAFF
            or 0xFF01 <= cp <= 0xFF60
            or 0x3000 <= cp <= 0x303F
        ):
            w += 2
        else:
            w += 1
    return w


def _normalized_result(result: dict) -> dict:
    """Return a shallow copy with a canonical recommendation label."""
    normalized = dict(result)
    normalized["investment_recommendation"] = normalize_recommendation(
        normalized.get("investment_recommendation", DEFAULT_RECOMMENDATION)
    )
    return normalized


def _normalized_vote_result(vote_result: dict) -> dict:
    """Return a shallow copy with canonical recommendation labels."""
    normalized = dict(vote_result)

    consensus = dict(normalized.get("consensus", {}))
    if consensus:
        consensus["recommendation"] = normalize_recommendation(
            consensus.get("recommendation", DEFAULT_RECOMMENDATION)
        )
        normalized["consensus"] = consensus

    individual_results = []
    for entry in normalized.get("individual_results", []):
        copied = dict(entry)
        if isinstance(copied.get("result"), dict):
            copied["result"] = _normalized_result(copied["result"])
        individual_results.append(copied)
    normalized["individual_results"] = individual_results
    return normalized


def _recommendation_icon(recommendation: str) -> str:
    bucket = recommendation_bucket(recommendation)
    if bucket == "positive":
        return "🤓"
    if bucket == "negative":
        return "😭"
    return "🤔"


def _recommendation_style(recommendation: str) -> str:
    bucket = recommendation_bucket(recommendation)
    if bucket == "positive":
        return "bold green"
    if bucket == "negative":
        return "bold red"
    return "bold"


def _rec_styled(recommendation: str, c) -> str:
    """Return recommendation with emoji and color."""
    recommendation = normalize_recommendation(recommendation)
    bucket = recommendation_bucket(recommendation)
    if bucket == "positive":
        return f"{_recommendation_icon(recommendation)} {c(_GREEN + _BOLD, recommendation)}"
    if bucket == "negative":
        return f"{_recommendation_icon(recommendation)} {c(_RED + _BOLD, recommendation)}"
    return f"{_recommendation_icon(recommendation)} {c(_BOLD, recommendation)}"


def _inspection_type(input_type: str, inspection: dict | None) -> str | None:
    if not inspection:
        return None
    if input_type == "github":
        return "github"
    if input_type == "web":
        return "web"
    return None


def _github_title(inspection: dict) -> str:
    return f"{inspection.get('owner', '?')}/{inspection.get('repo', '?')}"


def _web_title(inspection: dict) -> str:
    return inspection.get("title") or inspection.get("url", "?")


def _report_title(result: dict, inspection: dict | None, input_type: str) -> str:
    inspection_kind = _inspection_type(input_type, inspection)
    if inspection_kind == "github" and inspection:
        return _github_title(inspection)
    if inspection_kind == "web" and inspection:
        return _web_title(inspection)
    return result.get("primary_product") or "分析报告"


def _product_overview_paragraphs(result: dict) -> list[str]:
    """Collect short overview paragraphs shown before evidence."""
    paragraphs: list[str] = []
    seen: set[str] = set()

    for key in ("product_reality", "product_experience", "code_reality"):
        value = str(result.get(key) or "").strip()
        if value and value not in seen:
            paragraphs.append(value)
            seen.add(value)
    return paragraphs


def _information_completeness_text(level: str | None) -> str:
    return _INFO_COMPLETENESS_COPY.get(level or "", "")


def _result_body_lines(result: dict, c, lines: list[str], *, show_type: bool = True) -> None:
    """Render the analysis report body for terminal output."""
    normalized = _normalized_result(result)
    article_type = normalized.get("article_type", "unknown")
    primary_product = normalized.get("primary_product") or "-"
    recommendation = normalized.get("investment_recommendation", DEFAULT_RECOMMENDATION)
    info_level = normalized.get("information_completeness")

    type_label = _type_label(article_type)
    lines.append(f"  {c(_BOLD, primary_product)}")
    if show_type:
        lines.append(f"  来源: {type_label}")
    lines.append("")

    verdict = normalized.get("verdict", "")
    if verdict:
        pad = max(1, 30 - _display_width("判断"))
        lines.append(c(_DIM, f"── 判断 " + "─" * pad))
        lines.append("")
        lines.append(f"  {c(_BOLD, verdict)}")
        lines.append("")

    pad = max(1, 30 - _display_width("投资建议"))
    lines.append(c(_DIM, f"── 投资建议 " + "─" * pad))
    lines.append("")
    lines.append(f"  {_rec_styled(recommendation, c)}")
    lines.append("")

    overview = _product_overview_paragraphs(normalized)
    if overview:
        pad = max(1, 30 - _display_width("产品实况"))
        lines.append(c(_DIM, f"── 产品实况 " + "─" * pad))
        lines.append("")
        for paragraph in overview:
            lines.append(f"  {paragraph}")
            lines.append("")

    if article_type == "non_evaluable":
        return

    evidence = normalized.get("evidence", [])
    if evidence:
        pad = max(1, 30 - _display_width("关键证据"))
        lines.append(c(_DIM, f"── 关键证据 " + "─" * pad))
        lines.append("")
        for index, e in enumerate(evidence, start=1):
            etype = e.get("type", "fact")
            quote = e.get("quote", "")
            claim = e.get("claim", "")
            type_label_e = _EVIDENCE_TYPE_ZH.get(etype, etype)
            if etype == "risk":
                tag = c(_RED + _BOLD, f"[{type_label_e}]")
            elif etype in ("code_inspection", "product_testing", "promotional"):
                tag = c(_BOLD, f"[{type_label_e}]")
            else:
                tag = c(_DIM, f"[{type_label_e}]")
            lines.append(f"  {index}. {tag} {claim}")
            if quote:
                lines.append(c(_DIM, f"     「{quote}」"))
        lines.append("")

    ad_confidence = normalized.get("advertorial_confidence")
    ad_signals = normalized.get("advertorial_signals", [])
    if ad_confidence or ad_signals:
        pad = max(1, 30 - _display_width("广告信号"))
        lines.append(c(_DIM, f"── 广告信号 " + "─" * pad))
        lines.append("")
        if ad_confidence:
            lines.append(f"  广告置信度: {ad_confidence}")
        for s in ad_signals:
            lines.append(f"  · {s}")
        lines.append("")

    if info_level:
        pad = max(1, 30 - _display_width("信息完整度"))
        lines.append(c(_DIM, f"── 信息完整度 " + "─" * pad))
        lines.append("")
        lines.append(f"  {info_level}")
        summary = _information_completeness_text(info_level)
        if summary:
            lines.append("")
            lines.append(f"  {summary}")
        lines.append("")

    _render_interactive_section(normalized, c, lines)


def _render_interactive_section(result: dict, c, lines: list[str]) -> None:
    """Render the interactive Q&A section if present."""
    interactive = result.get("_interactive")
    if not interactive:
        return

    asked = interactive.get("questions_asked", 0)
    answered = interactive.get("questions_answered", 0)
    answers = interactive.get("answers", [])

    if not answers:
        return

    title = f"补充信息 (问 {asked} / 答 {answered})"
    pad = max(1, 30 - _display_width(title))
    lines.append(c(_DIM, f"─── {title} " + "─" * pad))
    lines.append(c(_DIM, "  以下信息来自用户补充，非原始材料"))
    for a in answers:
        lines.append(f"  Q: {a['question']}")
        lines.append(f"  A: {c(_BOLD, a['answer'])}")
        lines.append("")


def _render_vote_body(vote_result: dict, c, lines: list[str]) -> None:
    """Render consensus + per-model results for terminal output."""
    normalized = _normalized_vote_result(vote_result)
    consensus = normalized.get("consensus", {})
    individual = normalized.get("individual_results", [])

    agreement = consensus.get("agreement", "split")
    agreement_label = {
        "unanimous": "一致同意",
        "majority": "多数同意",
        "split": "意见分裂",
    }.get(agreement, agreement)

    rec = consensus.get("recommendation", DEFAULT_RECOMMENDATION)
    details = consensus.get("details", "")

    lines.append(c(_DIM, "──── 共识 " + "─" * 28))
    lines.append(f"  投票结果: {c(_BOLD, agreement_label)}")
    lines.append(f"  结论: {_rec_styled(rec, c)}")
    if details:
        lines.append(f"  详情: {details}")
    lines.append("")

    for entry in individual:
        prov = entry.get("provider", "?")
        lines.append(c(_DIM, f"──── {prov} " + "─" * max(1, 33 - _display_width(prov))))

        if "error" in entry:
            lines.append(c(_RED, f"  错误: {entry['error']}"))
        else:
            result = _normalized_result(entry.get("result", {}))
            r = result.get("investment_recommendation", DEFAULT_RECOMMENDATION)
            lines.append(f"  结论: {_rec_styled(r, c)}")
            code_reality = result.get("code_reality", "")
            if code_reality:
                lines.append(f"  代码真相: {code_reality}")
            product_exp = result.get("product_experience", "")
            if product_exp:
                lines.append(f"  产品体验: {product_exp}")
            reality = result.get("product_reality", "")
            if reality:
                lines.append(f"  说人话: {reality}")
            verdict = result.get("verdict", "")
            if verdict:
                lines.append(f"  判断: {verdict}")
        lines.append("")


def _format_inspection_section(inspection: dict, c) -> list[str]:
    """Render the GitHub inspection summary block for terminal output."""
    from funeralai.inspector import format_languages

    lines: list[str] = []
    api = inspection.get("api", {})
    owner = inspection.get("owner", "?")
    repo = inspection.get("repo", "?")
    stars = api.get("stars", 0)
    forks = api.get("forks", 0)

    pad = max(1, 30 - _display_width("代码实查"))
    lines.append(c(_DIM, f"─── 代码实查 " + "─" * pad))
    lines.append(f"  仓库: {c(_BOLD, f'{owner}/{repo}')} | Stars: {stars:,} | Forks: {forks:,}")

    languages = api.get("languages", {})
    if languages:
        lang_str = format_languages(languages)
        if lang_str != "无数据":
            lines.append(f"  语言: {lang_str}")

    contributors = api.get("contributors", [])
    if contributors:
        total_c = sum(ct["contributions"] for ct in contributors)
        if total_c > 0:
            top = contributors[0]
            pct = top["contributions"] / total_c * 100
            lines.append(f"  贡献者: {len(contributors)} 人 ({top['login']} 占 {pct:.0f}%)")

    totals = inspection.get("totals", {})
    total_files = inspection.get("total_files", 0)
    if total_files > 0:
        code_ratio = totals.get("code_ratio", 0)
        ratio_color = _RED if code_ratio < 30 else _GREEN if code_ratio > 60 else _YELLOW
        lines.append(f"  文件: {total_files} | 总行数: ~{totals.get('total', 0):,}")
        lines.append(
            f"  代码: ~{totals.get('code', 0):,} ({c(ratio_color, f'{code_ratio:.0f}%')}) | "
            f"文档: ~{totals.get('doc', 0):,} | 模板: ~{totals.get('template', 0):,} | 配置: ~{totals.get('config', 0):,}"
        )

    tests = inspection.get("tests", {})
    if tests.get("has_tests"):
        lines.append(c(_GREEN, f"  测试: ✓ {tests.get('test_file_count', 0)} 个测试文件"))
    else:
        lines.append(c(_RED, "  测试: ❌ 未发现"))

    build = inspection.get("build", {})
    if build.get("ci_systems"):
        lines.append(f"  CI: ✓ {', '.join(build['ci_systems'])}")
    if build.get("build_systems"):
        lines.append(f"  构建: {', '.join(build['build_systems'])}")

    red_flags = inspection.get("red_flags", [])
    if red_flags:
        lines.append("")
        for flag in red_flags:
            lines.append(c(_RED, f"  🚩 {flag}"))

    lines.append("")
    return lines


def _format_web_inspection_section(inspection: dict, c) -> list[str]:
    """Render the web inspection summary block for terminal output."""
    lines: list[str] = []
    url = inspection.get("url", "?")
    title = inspection.get("title") or "无标题"

    pad = max(1, 30 - _display_width("产品体验实查"))
    lines.append(c(_DIM, f"─── 产品体验实查 " + "─" * pad))
    lines.append(f"  URL: {c(_BOLD, url)}")
    lines.append(f"  标题: {title}")

    status = inspection.get("status_code")
    if status:
        status_color = _GREEN if status < 400 else _RED
        lines.append(f"  状态码: {c(status_color, str(status))}")

    response_time = inspection.get("response_time_ms")
    if response_time:
        time_color = _GREEN if response_time < 2000 else _YELLOW if response_time < 5000 else _RED
        lines.append(f"  响应时间: {c(time_color, f'{response_time}ms')}")

    content_len = inspection.get("content_length", 0)
    lines.append(f"  内容长度: {content_len:,} 字符")

    if inspection.get("redirected"):
        final = inspection.get("final_url", "?")
        if inspection.get("redirect_domain_changed"):
            lines.append(c(_YELLOW, f"  重定向: 跨域 → {final}"))
        else:
            lines.append(f"  重定向: → {final}")

    if inspection.get("blocked"):
        lines.append(c(_RED, "  反爬拦截: ✗ 被拦截"))

    browser = inspection.get("browser")
    if browser and not browser.get("error"):
        load_ms = browser.get("page_load_ms")
        if load_ms:
            load_color = _GREEN if load_ms < 2000 else _YELLOW if load_ms < 5000 else _RED
            lines.append(f"  页面加载: {c(load_color, f'{load_ms}ms')}")

        js_errors = browser.get("js_errors", [])
        if js_errors:
            lines.append(c(_RED, f"  JS 错误: {len(js_errors)} 个"))
        else:
            lines.append(c(_GREEN, "  JS 错误: 无"))

        res = browser.get("resource_stats", {})
        failed = res.get("failed", 0)
        if failed:
            lines.append(c(_RED, f"  资源: {res.get('total', 0)} 个 (失败 {failed})"))
        else:
            lines.append(f"  资源: {res.get('total', 0)} 个")

        ie = browser.get("interactive_elements", {})
        total_ie = ie.get("forms", 0) + ie.get("buttons", 0) + ie.get("inputs", 0)
        ie_color = _GREEN if total_ie > 0 else _RED
        lines.append(
            c(
                ie_color,
                f"  交互元素: 表单 {ie.get('forms', 0)} / "
                f"按钮 {ie.get('buttons', 0)} / "
                f"输入框 {ie.get('inputs', 0)}",
            )
        )

        lh = browser.get("link_health", {})
        if lh.get("checked", 0) > 0:
            broken = lh.get("broken", 0)
            link_color = _GREEN if broken == 0 else _RED
            lines.append(
                c(
                    link_color,
                    f"  链接健康: {lh['checked'] - broken}/{lh['checked']} 可访问",
                )
            )
    elif not inspection.get("browser_tested", False):
        lines.append(c(_DIM, "  浏览器测试: 未启用"))

    red_flags = inspection.get("red_flags", [])
    if red_flags:
        lines.append("")
        for flag in red_flags:
            lines.append(c(_RED, f"  🚩 {flag}"))

    lines.append("")
    return lines


def _format_terminal_inspected(
    result: dict,
    inspection: dict,
    title: str,
    inspection_renderer,
    extra_fields: list[tuple[str, str]],
) -> str:
    """Shared formatter for inspection-based analysis (GitHub / Web)."""
    c = _make_c()
    lines: list[str] = []

    lines.append("")
    lines.append(c(_BOLD, "═" * 39))
    lines.append(c(_BOLD, f"  葬AI 分析报告 — {title}"))
    lines.append(c(_BOLD, "═" * 39))
    lines.append("")

    lines.extend(inspection_renderer(inspection, c))

    normalized = _normalized_result(result)
    for field_key, field_label in extra_fields:
        value = normalized.get(field_key)
        if value:
            lines.append(f"  {field_label}: {c(_BOLD, value)}")
            lines.append("")

    _result_body_lines(normalized, c, lines, show_type=False)
    return "\n".join(lines)


def _format_vote_terminal_inspected(
    vote_result: dict,
    inspection: dict,
    title: str,
    inspection_renderer,
) -> str:
    """Shared formatter for inspection-based vote reports (GitHub / Web)."""
    c = _make_c()
    lines: list[str] = []

    lines.append("")
    lines.append(c(_BOLD, "═" * 39))
    lines.append(c(_BOLD, f"  葬AI 多模型投票报告 — {title}"))
    lines.append(c(_BOLD, "═" * 39))
    lines.append("")

    lines.extend(inspection_renderer(inspection, c))
    _render_vote_body(vote_result, c, lines)
    return "\n".join(lines)


def format_terminal(result: dict) -> str:
    """Format result as a human-readable terminal report in Chinese."""
    c = _make_c()
    lines: list[str] = []

    lines.append("")
    lines.append(c(_BOLD, "═" * 39))
    lines.append(c(_BOLD, "  葬AI 分析报告"))
    lines.append(c(_BOLD, "═" * 39))
    lines.append("")

    _result_body_lines(result, c, lines)
    return "\n".join(lines)


def format_batch_terminal(results: list[dict]) -> str:
    """Format batch results: one report block per file + summary."""
    c = _make_c()
    lines: list[str] = []

    success = 0
    fail = 0

    for entry in results:
        path = entry.get("file", "?")
        lines.append(c(_BOLD, f"\n{'═' * 39}"))
        lines.append(c(_BOLD, f"  {path}"))
        lines.append(c(_BOLD, "═" * 39))

        if "error" in entry:
            fail += 1
            lines.append(c(_RED, f"  错误: {entry['error']}"))
            lines.append("")
        else:
            success += 1
            lines.append(format_terminal(entry["result"]))

    lines.append(c(_BOLD, f"\n{'─' * 39}"))
    lines.append(c(_BOLD, f"  汇总: {success} 成功, {fail} 失败, 共 {len(results)} 个文件"))
    lines.append("")

    return "\n".join(lines)


def format_batch_json(results: list[dict]) -> str:
    """Format batch results as a JSON array."""
    return format_json(results)


def format_vote_terminal(vote_result: dict) -> str:
    """Format vote results: consensus summary + per-model conclusions."""
    c = _make_c()
    lines: list[str] = []

    lines.append("")
    lines.append(c(_BOLD, "═" * 39))
    lines.append(c(_BOLD, "  葬AI 多模型投票报告"))
    lines.append(c(_BOLD, "═" * 39))
    lines.append("")

    _render_vote_body(vote_result, c, lines)
    return "\n".join(lines)


def format_vote_json(vote_result: dict) -> str:
    """Format vote results as JSON."""
    return format_json(vote_result)


def format_terminal_github(result: dict, inspection: dict) -> str:
    """Format GitHub analysis result: inspection block + standard analysis."""
    return _format_terminal_inspected(
        result,
        inspection,
        title=_github_title(inspection),
        inspection_renderer=_format_inspection_section,
        extra_fields=[("code_reality", "代码真相")],
    )


def format_vote_terminal_github(vote_result: dict, inspection: dict) -> str:
    """Format GitHub vote results: inspection block + per-model conclusions."""
    return _format_vote_terminal_inspected(
        vote_result,
        inspection,
        title=_github_title(inspection),
        inspection_renderer=_format_inspection_section,
    )


def format_terminal_web(result: dict, inspection: dict) -> str:
    """Format web URL analysis result: inspection block + standard analysis."""
    return _format_terminal_inspected(
        result,
        inspection,
        title=_web_title(inspection),
        inspection_renderer=_format_web_inspection_section,
        extra_fields=[("product_experience", "产品体验")],
    )


def format_vote_terminal_web(vote_result: dict, inspection: dict) -> str:
    """Format web URL vote results: inspection block + per-model conclusions."""
    return _format_vote_terminal_inspected(
        vote_result,
        inspection,
        title=_web_title(inspection),
        inspection_renderer=_format_web_inspection_section,
    )


def _md_title(title: str, level: int = 1) -> str:
    return f"{'#' * level} {title}"


def _md_quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in str(text).splitlines())


def _md_inline(text: Any) -> str:
    return str(text).replace("\n", " ").strip()


def _md_table_cell(text: Any) -> str:
    return _md_inline(text).replace("|", "\\|") or "-"


def _batch_markdown_sections(results: list[dict], level: int = 2) -> list[str]:
    sections: list[str] = []
    success = 0
    fail = 0

    for entry in results:
        path = entry.get("file", "?")
        sections.append(_md_title(path, level=level))
        if "error" in entry:
            fail += 1
            sections.append(f"- 状态: 失败")
            sections.append(f"- 错误: {_md_inline(entry['error'])}")
        else:
            success += 1
            sections.append(f"- 状态: 成功")
            sections.append("")
            sections.append(_markdown_body(entry["result"], None, "local", heading_level=level + 1))
        sections.append("")

    sections.append(_md_title("汇总", level=level))
    sections.append(f"- 成功: {success}")
    sections.append(f"- 失败: {fail}")
    sections.append(f"- 总数: {len(results)}")
    return sections


def _markdown_inspection_lines(
    inspection: dict,
    input_type: str,
    *,
    level: int = 2,
) -> list[str]:
    lines: list[str] = []
    if input_type == "github":
        from funeralai.inspector import format_languages

        api = inspection.get("api", {})
        lines.append(_md_title("代码实查", level=level))
        lines.append(f"- 仓库: `{inspection.get('owner', '?')}/{inspection.get('repo', '?')}`")
        lines.append(f"- Stars: {api.get('stars', 0):,}")
        lines.append(f"- Forks: {api.get('forks', 0):,}")

        languages = api.get("languages", {})
        if languages:
            lang_str = format_languages(languages)
            if lang_str != "无数据":
                lines.append(f"- 语言: {_md_inline(lang_str)}")

        tests = inspection.get("tests", {})
        lines.append(f"- 测试: {'发现测试文件' if tests.get('has_tests') else '未发现测试'}")

    elif input_type == "web":
        lines.append(_md_title("产品体验实查", level=level))
        lines.append(f"- URL: `{inspection.get('url', '?')}`")
        lines.append(f"- 标题: {_md_inline(inspection.get('title') or '无标题')}")
        if inspection.get("status_code"):
            lines.append(f"- 状态码: {inspection['status_code']}")
        if inspection.get("response_time_ms"):
            lines.append(f"- 响应时间: {inspection['response_time_ms']}ms")
        if inspection.get("content_length") is not None:
            lines.append(f"- 内容长度: {inspection.get('content_length', 0):,} 字符")

        browser = inspection.get("browser")
        if browser and not browser.get("error"):
            if browser.get("page_load_ms"):
                lines.append(f"- 页面加载: {browser['page_load_ms']}ms")
            js_errors = browser.get("js_errors", [])
            lines.append(f"- JS 错误: {'无' if not js_errors else f'{len(js_errors)} 个'}")

    red_flags = inspection.get("red_flags", [])
    if red_flags:
        lines.append("")
        lines.append(_md_title("红旗", level=level))
        for flag in red_flags:
            lines.append(f"- {_md_inline(flag)}")

    return lines


def _markdown_body(
    result: dict,
    inspection: dict | None,
    input_type: str,
    *,
    heading_level: int = 1,
) -> str:
    normalized = _normalized_result(result)
    sections: list[str] = []
    title = _report_title(normalized, inspection, input_type)
    overview = _product_overview_paragraphs(normalized)
    info_level = normalized.get("information_completeness")

    sections.append(_md_title(title, level=heading_level))
    sections.append("")

    if normalized.get("verdict"):
        sections.append(_md_title("判断", level=heading_level + 1))
        sections.append(normalized["verdict"].strip())
        sections.append("")

    sections.append(_md_title("投资建议", level=heading_level + 1))
    sections.append(
        f"{_recommendation_icon(normalized.get('investment_recommendation', DEFAULT_RECOMMENDATION))} "
        f"{normalized.get('investment_recommendation', DEFAULT_RECOMMENDATION)}"
    )
    sections.append("")

    if overview:
        sections.append(_md_title("产品实况", level=heading_level + 1))
        sections.extend(overview)
        sections.append("")

    if inspection:
        sections.extend(
            _markdown_inspection_lines(
                inspection,
                input_type,
                level=heading_level + 1,
            )
        )
        sections.append("")

    evidence = normalized.get("evidence", [])
    if evidence:
        sections.append(_md_title("关键证据", level=heading_level + 1))
        sections.append("")
        sections.append("| # | 证据 | 原文/数据 | 类型 |")
        sections.append("|---|------|----------|------|")
        for index, item in enumerate(evidence, start=1):
            label = _EVIDENCE_TYPE_ZH.get(item.get("type", "fact"), item.get("type", "fact"))
            sections.append(
                f"| {index} | {_md_table_cell(item.get('claim', ''))} | "
                f"{_md_table_cell(item.get('quote', ''))} | {label} |"
            )
        sections.append("")

    ad_confidence = normalized.get("advertorial_confidence")
    ad_signals = normalized.get("advertorial_signals", [])
    if ad_confidence or ad_signals:
        sections.append(_md_title("广告信号", level=heading_level + 1))
        if ad_confidence:
            sections.append(f"- 广告置信度：{ad_confidence}")
        for signal in ad_signals:
            sections.append(f"- {_md_inline(signal)}")
        sections.append("")

    if info_level:
        sections.append(_md_title("信息完整度", level=heading_level + 1))
        sections.append(info_level)
        summary = _information_completeness_text(info_level)
        if summary:
            sections.append("")
            sections.append(summary)
        sections.append("")

    interactive = normalized.get("_interactive", {})
    answers = interactive.get("answers", [])
    if answers:
        sections.append(_md_title("补充信息", level=heading_level + 1))
        for item in answers:
            sections.append(f"- Q: {_md_inline(item.get('question', ''))}")
            sections.append(f"  A: {_md_inline(item.get('answer', ''))}")
        sections.append("")

    return "\n".join(section.rstrip() for section in sections).rstrip() + "\n"


def format_markdown(result: dict) -> str:
    """Format a single local analysis as Markdown."""
    return _markdown_body(result, None, "local")


def format_markdown_github(result: dict, inspection: dict) -> str:
    """Format a GitHub analysis as Markdown."""
    return _markdown_body(result, inspection, "github")


def format_markdown_web(result: dict, inspection: dict) -> str:
    """Format a web analysis as Markdown."""
    return _markdown_body(result, inspection, "web")


def _markdown_vote_body(
    vote_result: dict,
    inspection: dict | None,
    input_type: str,
    *,
    heading_level: int = 1,
) -> str:
    normalized = _normalized_vote_result(vote_result)
    sections: list[str] = []
    title = _report_title({"primary_product": "多模型投票"}, inspection, input_type)

    sections.append(_md_title(f"{title} · 多模型投票", level=heading_level))
    sections.append("")

    if inspection:
        sections.extend(
            _markdown_inspection_lines(
                inspection,
                input_type,
                level=heading_level + 1,
            )
        )
        sections.append("")

    consensus = normalized.get("consensus", {})
    agreement = consensus.get("agreement", "split")
    agreement_label = {
        "unanimous": "一致同意",
        "majority": "多数同意",
        "split": "意见分裂",
    }.get(agreement, agreement)
    sections.append(_md_title("共识", level=heading_level + 1))
    sections.append(f"- 投票结果: {agreement_label}")
    sections.append(f"- 结论: {consensus.get('recommendation', DEFAULT_RECOMMENDATION)}")
    if consensus.get("details"):
        sections.append(f"- 详情: {_md_inline(consensus['details'])}")
    sections.append("")

    sections.append(_md_title("各模型结果", level=heading_level + 1))
    sections.append("")
    for entry in normalized.get("individual_results", []):
        provider = entry.get("provider", "?")
        sections.append(_md_title(provider, level=heading_level + 2))
        if "error" in entry:
            sections.append(f"- 错误: {_md_inline(entry['error'])}")
            sections.append("")
            continue

        result = entry.get("result", {})
        sections.append(f"- 结论: {result.get('investment_recommendation', DEFAULT_RECOMMENDATION)}")
        if result.get("product_reality"):
            sections.append(f"- 说人话: {_md_inline(result['product_reality'])}")
        if result.get("verdict"):
            sections.append(f"- 判断: {_md_inline(result['verdict'])}")
        sections.append("")

    return "\n".join(section.rstrip() for section in sections).rstrip() + "\n"


def format_vote_markdown(vote_result: dict) -> str:
    """Format a local vote report as Markdown."""
    return _markdown_vote_body(vote_result, None, "local")


def format_vote_markdown_github(vote_result: dict, inspection: dict) -> str:
    """Format a GitHub vote report as Markdown."""
    return _markdown_vote_body(vote_result, inspection, "github")


def format_vote_markdown_web(vote_result: dict, inspection: dict) -> str:
    """Format a web vote report as Markdown."""
    return _markdown_vote_body(vote_result, inspection, "web")


def format_batch_markdown(results: list[dict]) -> str:
    """Format batch results as Markdown."""
    sections = [_md_title("批量分析报告")]
    sections.append("")
    sections.extend(_batch_markdown_sections(results))
    return "\n".join(section.rstrip() for section in sections).rstrip() + "\n"


def _plain_text(text: str, style: str = "") -> Text:
    return Text(text, style=style)


def _kv_text(label: str, value: Any, *, label_style: str = "bold", value_style: str = "") -> Text:
    text = Text()
    text.append(f"{label}: ", style=label_style)
    text.append(str(value), style=value_style)
    return text


def _inspection_renderables(inspection: dict, input_type: str) -> list[RenderableType]:
    parts: list[RenderableType] = []
    if input_type == "github":
        from funeralai.inspector import format_languages

        api = inspection.get("api", {})
        parts.append(Rule("代码实查", style="dim"))
        parts.append(_kv_text("仓库", f"{inspection.get('owner', '?')}/{inspection.get('repo', '?')}", value_style="bold"))
        parts.append(_kv_text("Stars", f"{api.get('stars', 0):,}"))
        parts.append(_kv_text("Forks", f"{api.get('forks', 0):,}"))
        languages = api.get("languages", {})
        if languages:
            lang_str = format_languages(languages)
            if lang_str != "无数据":
                parts.append(_kv_text("语言", lang_str))

        tests = inspection.get("tests", {})
        parts.append(_kv_text("测试", "发现测试文件" if tests.get("has_tests") else "未发现测试"))

    elif input_type == "web":
        parts.append(Rule("产品体验实查", style="dim"))
        parts.append(_kv_text("URL", inspection.get("url", "?"), value_style="bold"))
        parts.append(_kv_text("标题", inspection.get("title") or "无标题"))
        if inspection.get("status_code"):
            parts.append(_kv_text("状态码", inspection["status_code"]))
        if inspection.get("response_time_ms"):
            parts.append(_kv_text("响应时间", f"{inspection['response_time_ms']}ms"))
        if inspection.get("content_length") is not None:
            parts.append(_kv_text("内容长度", f"{inspection.get('content_length', 0):,} 字符"))

        browser = inspection.get("browser")
        if browser and not browser.get("error"):
            if browser.get("page_load_ms"):
                parts.append(_kv_text("页面加载", f"{browser['page_load_ms']}ms"))
            js_errors = browser.get("js_errors", [])
            parts.append(_kv_text("JS 错误", "无" if not js_errors else f"{len(js_errors)} 个"))

    red_flags = inspection.get("red_flags", [])
    if red_flags:
        parts.append(Text())
        parts.append(Rule("红旗", style="dim"))
        for flag in red_flags:
            parts.append(_plain_text(f"• {flag}", style="red"))

    if parts:
        parts.append(Text())
    return parts


def _evidence_renderables(evidence: list[dict]) -> list[RenderableType]:
    parts: list[RenderableType] = []
    if not evidence:
        return parts

    parts.append(Rule("关键证据", style="dim"))
    for index, item in enumerate(evidence, start=1):
        label = _EVIDENCE_TYPE_ZH.get(item.get("type", "fact"), item.get("type", "fact"))
        bucket = item.get("type", "fact")
        tag_style = {
            "risk": "red",
            "promotional": "bold",
            "code_inspection": "bold",
            "product_testing": "bold",
        }.get(bucket, "dim")

        line = Text()
        line.append(f"{index}. ", style="dim")
        line.append(f"[{label}] ", style=tag_style)
        line.append(item.get("claim", "") or "-")
        parts.append(line)

        quote = item.get("quote", "")
        if quote:
            parts.append(Padding(Text(f"「{quote}」", style="dim"), (0, 0, 0, 4)))
    parts.append(Text())
    return parts


def _interactive_renderables(result: dict) -> list[RenderableType]:
    interactive = result.get("_interactive")
    if not interactive:
        return []

    answers = interactive.get("answers", [])
    if not answers:
        return []

    asked = interactive.get("questions_asked", 0)
    answered = interactive.get("questions_answered", 0)
    parts: list[RenderableType] = [
        Rule(f"补充信息 (问 {asked} / 答 {answered})", style="dim"),
        Text("以下信息来自用户补充，非原始材料", style="dim"),
    ]
    for item in answers:
        parts.append(_plain_text(f"Q: {item.get('question', '')}", style="bold"))
        parts.append(Padding(Text(f"A: {item.get('answer', '')}"), (0, 0, 0, 2)))
    parts.append(Text())
    return parts


def render_report(result: dict, inspection: dict | None = None, input_type: str = "local") -> RenderableType:
    """Build a width-safe Rich renderable for a single analysis report."""
    normalized = _normalized_result(result)
    parts: list[RenderableType] = []
    overview = _product_overview_paragraphs(normalized)
    title = _report_title(normalized, inspection, input_type)

    parts.append(Text(f"葬AI分析报告：{title}", style="bold"))

    meta = Text()
    article_type = normalized.get("article_type", "unknown")
    meta.append(f"来源: {_type_label(article_type)}", style="dim")
    parts.append(meta)
    parts.append(Text())

    if normalized.get("verdict"):
        parts.append(Rule("判断", style="dim"))
        parts.append(_plain_text(normalized["verdict"], style="bold"))
        parts.append(Text())

    parts.append(Rule("投资建议", style="dim"))
    rec = normalized.get("investment_recommendation", DEFAULT_RECOMMENDATION)
    rec_line = Text()
    rec_line.append(_recommendation_icon(rec) + " ")
    rec_line.append(rec, style=_recommendation_style(rec))
    parts.append(rec_line)
    parts.append(Text())

    if overview:
        parts.append(Rule("产品实况", style="dim"))
        for paragraph in overview:
            parts.append(_plain_text(paragraph))
            parts.append(Text())

    if inspection:
        parts.extend(_inspection_renderables(inspection, input_type))

    parts.extend(_evidence_renderables(normalized.get("evidence", [])))

    ad_confidence = normalized.get("advertorial_confidence")
    ad_signals = normalized.get("advertorial_signals", [])
    if ad_confidence or ad_signals:
        parts.append(Rule("广告信号", style="dim"))
        if ad_confidence:
            parts.append(_plain_text(f"广告置信度: {ad_confidence}"))
        for signal in ad_signals:
            parts.append(_plain_text(f"• {signal}"))
        parts.append(Text())

    info_level = normalized.get("information_completeness")
    if info_level:
        parts.append(Rule("信息完整度", style="dim"))
        parts.append(_plain_text(info_level, style="bold"))
        summary = _information_completeness_text(info_level)
        if summary:
            parts.append(Text())
            parts.append(_plain_text(summary))
        parts.append(Text())

    parts.extend(_interactive_renderables(normalized))
    return Group(*parts)


def render_vote_report(
    vote_result: dict,
    inspection: dict | None = None,
    input_type: str = "local",
) -> RenderableType:
    """Build a width-safe Rich renderable for a vote report."""
    normalized = _normalized_vote_result(vote_result)
    parts: list[RenderableType] = []

    if inspection:
        parts.extend(_inspection_renderables(inspection, input_type))

    consensus = normalized.get("consensus", {})
    agreement = consensus.get("agreement", "split")
    agreement_label = {
        "unanimous": "一致同意",
        "majority": "多数同意",
        "split": "意见分裂",
    }.get(agreement, agreement)

    parts.append(Rule("共识", style="dim"))
    parts.append(_kv_text("投票结果", agreement_label, value_style="bold"))

    rec = consensus.get("recommendation", DEFAULT_RECOMMENDATION)
    rec_line = Text()
    rec_line.append("结论: ", style="bold")
    rec_line.append(_recommendation_icon(rec) + " ")
    rec_line.append(rec, style=_recommendation_style(rec))
    parts.append(rec_line)
    if consensus.get("details"):
        parts.append(_kv_text("详情", consensus["details"]))
    parts.append(Text())

    parts.append(Rule("各模型结果", style="dim"))
    for entry in normalized.get("individual_results", []):
        provider = entry.get("provider", "?")
        parts.append(Text(provider, style="bold"))
        if "error" in entry:
            parts.append(Padding(Text(f"错误: {entry['error']}", style="red"), (0, 0, 0, 2)))
            parts.append(Text())
            continue

        result = _normalized_result(entry.get("result", {}))
        item_rec = result.get("investment_recommendation", DEFAULT_RECOMMENDATION)
        vote_line = Text()
        vote_line.append("结论: ", style="bold")
        vote_line.append(_recommendation_icon(item_rec) + " ")
        vote_line.append(item_rec, style=_recommendation_style(item_rec))
        parts.append(Padding(vote_line, (0, 0, 0, 2)))

        if result.get("product_reality"):
            parts.append(Padding(Text(f"说人话: {result['product_reality']}"), (0, 0, 0, 2)))
        if result.get("verdict"):
            parts.append(Padding(Text(f"判断: {result['verdict']}"), (0, 0, 0, 2)))
        parts.append(Text())

    return Group(*parts)


def render_batch_report(results: list[dict]) -> RenderableType:
    """Build a Rich renderable for batch analysis results."""
    parts: list[RenderableType] = [Rule("批量分析报告", style="dim"), Text()]
    for entry in results:
        parts.append(Text(entry.get("file", "?"), style="bold"))
        if "error" in entry:
            parts.append(Padding(Text(f"错误: {entry['error']}", style="red"), (0, 0, 0, 2)))
        else:
            parts.append(Padding(render_report(entry["result"]), (0, 0, 0, 2)))
        parts.append(Text())
    return Group(*parts)


def _slugify_part(text: str) -> str:
    """Turn an object label into a filesystem-friendly name."""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._-")
    return cleaned[:80] or "analysis"


def suggest_markdown_basename(
    result: dict | list[dict],
    inspection: dict | None = None,
    input_type: str = "local",
) -> str:
    """Suggest a default file basename for Markdown export."""
    if isinstance(result, list):
        return "batch_analysis"

    if isinstance(result, dict) and result.get("consensus"):
        title = _report_title({"primary_product": "多模型投票"}, inspection, input_type)
        return _slugify_part(title or "vote")

    if inspection and input_type == "github":
        return _slugify_part(_github_title(inspection))
    if inspection and input_type == "web":
        return _slugify_part(_web_title(inspection))
    if isinstance(result, dict) and result.get("primary_product"):
        return _slugify_part(str(result["primary_product"]))
    return "analysis"
