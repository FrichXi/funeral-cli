"""Command-line entry point for funeralai.

No subcommand → TUI interactive session (via tui.app).
``funeralai analyze <file_or_url>...`` → one-shot CLI analysis.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

from funeralai.auth import (
    can_prompt_for_credentials,
    classify_provider_error,
    find_vote_blocking_issues,
    is_blocking_credential_error,
    prompt_configure_credentials,
    replace_vote_provider,
)

# ---------------------------------------------------------------------------
# Input classification
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+")


def _is_github_url(s: str) -> bool:
    return bool(_GITHUB_RE.match(s))


def _is_web_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _classify_inputs(
    raw_inputs: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Split raw CLI positional args into (github_urls, web_urls, files)."""
    github_urls = [u for u in raw_inputs if _is_github_url(u)]
    web_urls = [u for u in raw_inputs if _is_web_url(u) and not _is_github_url(u)]
    others = [p for p in raw_inputs if not _is_web_url(p)]
    files = _resolve_files(others)
    return github_urls, web_urls, files


def _resolve_files(paths: list[str]) -> list[str]:
    """Expand directories and glob patterns into concrete file paths."""
    result: list[str] = []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            for ext in ("*.md", "*.txt", "*.pdf"):
                result.extend(
                    sorted(glob.glob(str(path / "**" / ext), recursive=True))
                )
        elif path.exists():
            result.append(str(path))
        else:
            # Try as a glob pattern
            matches = sorted(glob.glob(p))
            if matches:
                result.extend(matches)
            else:
                print(f"警告: 文件不存在: {p}", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a .env file into ``os.environ``."""
    env_path = Path(path).expanduser().resolve()
    if not env_path.is_file():
        print(f"警告: .env 文件不存在: {path}", file=sys.stderr)
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _run_analysis(
    text: str,
    provider: str | None,
    api_key: str | None,
    model: str | None,
    interactive: bool,
    prompt_version: int,
    red_flags: list[str] | None = None,
) -> dict | None:
    """Run a single analysis and return the result dict, or None on error."""
    from funeralai.analyzer import analyze

    current_provider = provider
    current_key = api_key

    while True:
        try:
            return analyze(
                text=text,
                api_key=current_key,
                model=model,
                provider=current_provider,
                interactive=interactive,
                prompt_version=prompt_version,
                red_flags=red_flags,
            )
        except Exception as exc:
            issue = classify_provider_error(
                exc,
                provider=current_provider or "",
                model=model or "",
            )
            if is_blocking_credential_error(exc) and can_prompt_for_credentials():
                result = prompt_configure_credentials(
                    current_provider,
                    reason=issue.message,
                )
                if result:
                    current_provider, current_key = result
                    continue
            print(f"错误: {issue.message}", file=sys.stderr)
            return None


def _run_vote(
    text: str,
    providers: list[str],
    model: str | None,
    prompt_version: int,
    red_flags: list[str] | None = None,
    format_mode: str = "terminal",
) -> dict | None:
    """Run a multi-model vote and return the result dict, or None on error."""
    from funeralai.analyzer import analyze_vote

    current_providers = list(providers)

    while True:
        try:
            vote_result = analyze_vote(
                text=text,
                providers=current_providers,
                model=model,
                prompt_version=prompt_version,
                interactive=False,
                red_flags=red_flags,
            )
        except Exception as exc:
            print(f"投票分析失败: {exc}", file=sys.stderr)
            return None

        blocking = find_vote_blocking_issues(vote_result)
        if not blocking or not can_prompt_for_credentials(format_mode):
            return vote_result

        target = blocking[0]
        configured = prompt_configure_credentials(
            target.provider,
            reason=target.issue.message,
        )
        if not configured:
            return None

        new_provider, _ = configured
        current_providers = replace_vote_provider(
            current_providers,
            target.provider,
            new_provider,
        )
        if len(current_providers) < 2:
            print(
                "错误: 修复投票 Provider 后，剩余不同 provider 少于 2 个。",
                file=sys.stderr,
            )
            return None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _output_single(
    result: dict,
    inspection: dict | None,
    input_type: str,
    format_mode: str,
) -> None:
    """Print a single analysis result to stdout."""
    if format_mode == "json":
        from funeralai.output import format_json

        print(format_json(result))
    elif format_mode == "markdown":
        from funeralai.exporting import render_markdown

        print(render_markdown(result, inspection, input_type))
    elif input_type == "github" and inspection is not None:
        from funeralai.output import format_terminal_github

        print(format_terminal_github(result, inspection))
    elif input_type == "web" and inspection is not None:
        from funeralai.output import format_terminal_web

        print(format_terminal_web(result, inspection))
    else:
        from funeralai.output import format_terminal

        print(format_terminal(result))


def _output_vote(
    vote_result: dict,
    inspection: dict | None,
    input_type: str,
    format_mode: str,
) -> None:
    """Print a vote result to stdout."""
    if format_mode == "json":
        from funeralai.output import format_vote_json

        print(format_vote_json(vote_result))
    elif format_mode == "markdown":
        from funeralai.exporting import render_markdown

        print(render_markdown(vote_result, inspection, input_type))
    elif input_type == "github" and inspection is not None:
        from funeralai.output import format_vote_terminal_github

        print(format_vote_terminal_github(vote_result, inspection))
    elif input_type == "web" and inspection is not None:
        from funeralai.output import format_vote_terminal_web

        print(format_vote_terminal_web(vote_result, inspection))
    else:
        from funeralai.output import format_vote_terminal

        print(format_vote_terminal(vote_result))


# ---------------------------------------------------------------------------
# Per-input-type dispatch
# ---------------------------------------------------------------------------


def _analyze_github(
    url: str,
    provider: str | None,
    api_key: str | None,
    model: str | None,
    args: argparse.Namespace,
    vote_providers: list[str] | None,
    format_mode: str,
) -> int:
    """Inspect a GitHub repo and run the analysis pipeline."""
    try:
        from funeralai.inspector import inspect_github
    except ImportError:
        print(
            "GitHub 实查需要 git CLI，请确认 git 已安装",
            file=sys.stderr,
        )
        return 1

    try:
        inspection, readme, report = inspect_github(
            url, no_clone=getattr(args, "no_clone", False)
        )
    except Exception as exc:
        print(f"GitHub 实查失败: {exc}", file=sys.stderr)
        return 1

    text = f"## 项目 README\n\n{readme}\n\n{report}"
    red_flags = inspection.get("red_flags", [])

    if vote_providers:
        result = _run_vote(
            text,
            vote_providers,
            model,
            prompt_version=2,
            red_flags=red_flags,
            format_mode=format_mode,
        )
        if result is None:
            return 1
        _output_vote(result, inspection, "github", format_mode)
    else:
        result = _run_analysis(
            text,
            provider,
            api_key,
            model,
            interactive=args.ask,
            prompt_version=2,
            red_flags=red_flags,
        )
        if result is None:
            return 1
        _output_single(result, inspection, "github", format_mode)

    return 0


def _analyze_web(
    url: str,
    provider: str | None,
    api_key: str | None,
    model: str | None,
    args: argparse.Namespace,
    vote_providers: list[str] | None,
    format_mode: str,
) -> int:
    """Inspect a web URL and run the analysis pipeline."""
    try:
        from funeralai.scraper import inspect_web
    except ImportError:
        print(
            "网页分析缺少依赖 httpx，请重新安装：\n  pip install funeralai",
            file=sys.stderr,
        )
        return 1

    try:
        inspection, page_content, report = inspect_web(
            url, no_browser=getattr(args, "no_browser", False)
        )
    except Exception as exc:
        print(f"网页实查失败: {exc}", file=sys.stderr)
        return 1

    text = f"## 网页内容\n\n{page_content}\n\n{report}"
    red_flags = inspection.get("red_flags", [])

    if vote_providers:
        result = _run_vote(
            text,
            vote_providers,
            model,
            prompt_version=3,
            red_flags=red_flags,
            format_mode=format_mode,
        )
        if result is None:
            return 1
        _output_vote(result, inspection, "web", format_mode)
    else:
        result = _run_analysis(
            text,
            provider,
            api_key,
            model,
            interactive=args.ask,
            prompt_version=3,
            red_flags=red_flags,
        )
        if result is None:
            return 1
        _output_single(result, inspection, "web", format_mode)

    return 0


def _analyze_single_file(
    filepath: str,
    provider: str | None,
    api_key: str | None,
    model: str | None,
    args: argparse.Namespace,
    vote_providers: list[str] | None,
    format_mode: str,
) -> int:
    """Read a local file and run the analysis pipeline."""
    from funeralai.reader import read_file

    try:
        text = read_file(filepath)
    except Exception as exc:
        print(f"读取失败: {filepath}: {exc}", file=sys.stderr)
        return 1

    if not text.strip():
        print(f"警告: 文件内容为空: {filepath}", file=sys.stderr)
        return 1

    if vote_providers:
        result = _run_vote(
            text,
            vote_providers,
            model,
            prompt_version=1,
            format_mode=format_mode,
        )
        if result is None:
            return 1
        _output_vote(result, None, "local", format_mode)
    else:
        result = _run_analysis(
            text,
            provider,
            api_key,
            model,
            interactive=args.ask,
            prompt_version=1,
        )
        if result is None:
            return 1
        _output_single(result, None, "local", format_mode)

    return 0


def _analyze_direct_text(
    text: str,
    provider: str | None,
    api_key: str | None,
    model: str | None,
    args: argparse.Namespace,
    vote_providers: list[str] | None,
    format_mode: str,
) -> int:
    """Analyze directly-provided text content."""
    if not text.strip():
        print("警告: --text 内容为空", file=sys.stderr)
        return 1

    if vote_providers:
        result = _run_vote(
            text,
            vote_providers,
            model,
            prompt_version=1,
            format_mode=format_mode,
        )
        if result is None:
            return 1
        _output_vote(result, None, "local", format_mode)
    else:
        result = _run_analysis(
            text,
            provider,
            api_key,
            model,
            interactive=args.ask,
            prompt_version=1,
        )
        if result is None:
            return 1
        _output_single(result, None, "local", format_mode)

    return 0


def _analyze_batch(
    files: list[str],
    provider: str | None,
    api_key: str | None,
    model: str | None,
    args: argparse.Namespace,
    format_mode: str,
) -> int:
    """Run batch (serial) analysis across multiple local files."""
    from funeralai.analyzer import analyze_batch

    try:
        results = analyze_batch(
            files, api_key=api_key, model=model, provider=provider
        )
    except Exception as exc:
        print(f"批量分析失败: {exc}", file=sys.stderr)
        return 1

    if format_mode == "json":
        from funeralai.output import format_batch_json

        print(format_batch_json(results))
    elif format_mode == "markdown":
        from funeralai.exporting import render_markdown

        print(render_markdown(results))
    else:
        from funeralai.output import format_batch_terminal

        print(format_batch_terminal(results))

    return 0


# ---------------------------------------------------------------------------
# Top-level analyze command
# ---------------------------------------------------------------------------


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Execute the ``analyze`` subcommand."""
    from funeralai.analyzer import _resolve_provider

    # Load .env file if specified
    if args.env_file:
        _load_env_file(args.env_file)

    # Quiet mode
    if args.quiet:
        os.environ["FUNERALAI_QUIET"] = "1"

    # Handle --text (including stdin via "-")
    text_input: str | None = None
    if args.text is not None:
        text_input = sys.stdin.read() if args.text == "-" else args.text

    # Classify positional inputs
    raw_inputs: list[str] = args.file_or_url or []
    github_urls, web_urls, files = _classify_inputs(raw_inputs)

    # Validate: must have something to analyze
    if text_input is not None and not text_input.strip():
        print("错误: --text 内容为空", file=sys.stderr)
        return 1
    if not text_input and not github_urls and not web_urls and not files:
        print("错误: 请提供文件、URL 或 --text 参数", file=sys.stderr)
        return 1

    # Provider / model
    provider = args.provider
    api_key = args.api_key
    model = args.model

    # Vote mode
    vote_providers: list[str] | None = None
    if args.vote:
        vote_providers = [p.strip() for p in args.vote.split(",")]
        if len(vote_providers) < 2:
            print(
                "错误: --vote 需要至少 2 个 provider（逗号分隔）",
                file=sys.stderr,
            )
            return 1

    format_mode: str = args.format or "terminal"
    exit_code = 0

    if not args.vote:
        try:
            provider, api_key = _resolve_provider(provider, api_key)
        except RuntimeError as exc:
            issue = classify_provider_error(
                exc,
                provider=provider or "",
                model=model or "",
            )
            if can_prompt_for_credentials(format_mode):
                configured = prompt_configure_credentials(
                    provider,
                    reason=issue.message,
                )
                if configured:
                    provider, api_key = configured
                else:
                    return 1
            else:
                print(f"错误: {issue.message}", file=sys.stderr)
                return 1

    # ---- GitHub URLs ----
    for url in github_urls:
        code = _analyze_github(
            url, provider, api_key, model, args, vote_providers, format_mode
        )
        if code != 0:
            exit_code = code

    # ---- Web URLs ----
    for url in web_urls:
        code = _analyze_web(
            url, provider, api_key, model, args, vote_providers, format_mode
        )
        if code != 0:
            exit_code = code

    # ---- Local files ----
    if files:
        if len(files) > 1 and not vote_providers:
            code = _analyze_batch(
                files, provider, api_key, model, args, format_mode
            )
            if code != 0:
                exit_code = code
        else:
            for f in files:
                code = _analyze_single_file(
                    f, provider, api_key, model, args, vote_providers, format_mode
                )
                if code != 0:
                    exit_code = code

    # ---- Direct text ----
    if text_input:
        code = _analyze_direct_text(
            text_input, provider, api_key, model, args, vote_providers, format_mode
        )
        if code != 0:
            exit_code = code

    return exit_code


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with the ``analyze`` subcommand."""
    from funeralai import __version__

    parser = argparse.ArgumentParser(
        prog="funeralai",
        description="funeralai - AI product analysis agent. 整点真实.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"funeralai {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ---- analyze subcommand ----
    analyze_p = subparsers.add_parser(
        "analyze",
        help="One-shot analysis of files, URLs, or text",
        description="Analyze files, GitHub repos, web URLs, or raw text.",
    )

    # Positional
    analyze_p.add_argument(
        "file_or_url",
        nargs="*",
        help="File paths, directories, GitHub URLs, or web URLs",
    )

    # Analysis options
    analysis_group = analyze_p.add_argument_group("analysis options")
    analysis_group.add_argument(
        "--text",
        metavar="TEXT",
        help='Pass text content directly; use "-" to read from stdin',
    )
    analysis_group.add_argument(
        "--ask",
        action="store_true",
        default=False,
        help="Enable interactive Q&A (default: off for CLI)",
    )
    analysis_group.add_argument(
        "--vote",
        metavar="PROVIDERS",
        help="Multi-model vote (comma-separated, e.g. gemini,deepseek,qwen)",
    )
    analysis_group.add_argument(
        "--no-clone",
        action="store_true",
        default=False,
        help="GitHub: skip clone, API metadata only",
    )
    analysis_group.add_argument(
        "--no-browser",
        action="store_true",
        default=False,
        help="Web: skip playwright browser testing",
    )

    # Provider / model
    provider_group = analyze_p.add_argument_group("provider/model")
    provider_group.add_argument(
        "--provider",
        metavar="PROVIDER",
        help="LLM provider (e.g. openai, anthropic, gemini, deepseek, qwen)",
    )
    provider_group.add_argument(
        "--api-key",
        metavar="KEY",
        help="API key (can also use environment variables)",
    )
    provider_group.add_argument(
        "--model",
        metavar="MODEL",
        help="Model name override",
    )
    provider_group.add_argument(
        "--env-file",
        metavar="PATH",
        help="Load environment variables from a .env file",
    )

    # Output
    output_group = analyze_p.add_argument_group("output")
    output_group.add_argument(
        "--format",
        choices=["json", "markdown", "terminal"],
        default="terminal",
        help="Output format (default: terminal)",
    )
    output_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=False,
        help="Quiet mode: suppress progress messages on stderr",
    )

    # Concurrency
    concurrency_group = analyze_p.add_argument_group("concurrency")
    concurrency_group.add_argument(
        "--workers",
        type=int,
        default=5,
        metavar="N",
        help="Max concurrent workers for batch/vote (default: 5)",
    )

    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    No subcommand → TUI interactive session.
    ``analyze`` subcommand → one-shot analysis.
    """
    args = _build_parser().parse_args(argv)

    if args.command is None:
        # No subcommand → launch TUI interactive session
        from funeralai.tui.app import run_app

        run_app()
        return 0

    if args.command == "analyze":
        return _cmd_analyze(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
