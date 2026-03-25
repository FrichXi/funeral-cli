"""Tests for funeralai.tui.intent — pure rule-based intent parsing."""

from __future__ import annotations

import os
import textwrap

import pytest

from funeralai.tui.intent import Intent, parse_intent


# ── helpers ──────────────────────────────────────────────────────────────────


def _type(raw: str) -> str:
    """Shortcut: return just the intent type for a given raw input."""
    return parse_intent(raw).type


# ── 1. GitHub URL → analyze_github ───────────────────────────────────────────


class TestGitHubURL:
    def test_basic_github_url(self):
        i = parse_intent("https://github.com/user/repo")
        assert i.type == "analyze_github"
        assert i.url == "https://github.com/user/repo"

    def test_github_url_with_path(self):
        i = parse_intent("https://github.com/user/repo/tree/main/src")
        assert i.type == "analyze_github"
        assert i.url == "https://github.com/user/repo/tree/main/src"

    def test_github_url_with_surrounding_text(self):
        i = parse_intent("看看这个 https://github.com/user/repo 怎么样")
        assert i.type == "analyze_github"
        assert i.url == "https://github.com/user/repo"

    def test_github_url_http(self):
        i = parse_intent("http://github.com/user/repo")
        assert i.type == "analyze_github"

    def test_github_url_trailing_punctuation(self):
        """Trailing dots/commas/semicolons should be stripped from the URL."""
        i = parse_intent("https://github.com/user/repo.")
        assert i.type == "analyze_github"
        assert i.url == "https://github.com/user/repo"


# ── 2. Web URL → analyze_web ────────────────────────────────────────────────


class TestWebURL:
    def test_basic_web_url(self):
        i = parse_intent("https://example.com/product")
        assert i.type == "analyze_web"
        assert i.url == "https://example.com/product"

    def test_http_url(self):
        i = parse_intent("http://some-startup.io/pricing")
        assert i.type == "analyze_web"

    def test_url_with_query_params(self):
        i = parse_intent("https://example.com/page?ref=twitter&id=42")
        assert i.type == "analyze_web"
        assert "ref=twitter" in i.url

    def test_url_embedded_in_text(self):
        i = parse_intent("分析一下 https://example.com 这个产品")
        assert i.type == "analyze_web"
        assert i.url == "https://example.com"

    def test_non_github_git_hosting(self):
        """GitLab, Bitbucket etc. are treated as web, not github."""
        i = parse_intent("https://gitlab.com/user/repo")
        assert i.type == "analyze_web"


# ── 3. Local file path → analyze_file ───────────────────────────────────────


class TestFilePath:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("hello")
        i = parse_intent(str(f))
        assert i.type == "analyze_file"
        assert i.path == str(f)

    def test_quoted_path(self, tmp_path):
        f = tmp_path / "my file.txt"
        f.write_text("content")
        i = parse_intent(f'"{f}"')
        assert i.type == "analyze_file"

    def test_single_quoted_path(self, tmp_path):
        f = tmp_path / "data.pdf"
        f.write_text("pdf content")
        i = parse_intent(f"'{f}'")
        assert i.type == "analyze_file"

    def test_nonexistent_path_is_not_file(self):
        """A path that doesn't exist should not match as analyze_file."""
        i = parse_intent("/tmp/this_file_definitely_does_not_exist_xyz.md")
        assert i.type != "analyze_file"


# ── 4. Directory → analyze_batch ────────────────────────────────────────────


class TestDirectoryBatch:
    def test_directory_with_supported_files(self, tmp_path):
        (tmp_path / "a.md").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        (tmp_path / "c.pdf").write_text("z")
        i = parse_intent(str(tmp_path))
        assert i.type == "analyze_batch"
        assert len(i.paths) == 3

    def test_directory_ignores_unsupported_extensions(self, tmp_path):
        (tmp_path / "a.md").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.jpg").write_text("z")
        i = parse_intent(str(tmp_path))
        assert i.type == "analyze_batch"
        assert len(i.paths) == 1  # only .md

    def test_empty_directory(self, tmp_path):
        i = parse_intent(str(tmp_path))
        assert i.type == "unclear"

    def test_directory_no_supported_files(self, tmp_path):
        (tmp_path / "image.png").write_text("binary")
        i = parse_intent(str(tmp_path))
        assert i.type == "unclear"


# ── 5. Long text (>=180 chars) → analyze_text ───────────────────────────────


class TestLongText:
    def test_exactly_180_chars(self):
        text = "a" * 180
        i = parse_intent(text)
        assert i.type == "analyze_text"
        assert i.text == text

    def test_over_180_chars(self):
        text = "这是一个非常长的产品描述。" * 20  # well over 180 chars
        assert _type(text) == "analyze_text"

    def test_179_chars_not_long_text(self):
        text = "a" * 179
        # 179 chars is below threshold, should be chat (unless multi-line rule kicks in)
        assert _type(text) == "chat"


# ── 6. Multi-line text (>=3 lines + >=80 chars) → analyze_text ──────────────


class TestMultilineText:
    def test_three_lines_over_80_chars(self):
        text = "line one here with more\nline two here with more\nline three here with more\nline four with enough"
        assert len(text.strip()) >= 80
        assert text.strip().count("\n") >= 3
        assert _type(text) == "analyze_text"

    def test_three_lines_under_80_chars(self):
        text = "a\nb\nc\nd"
        assert text.count("\n") >= 3
        assert len(text) < 80
        assert _type(text) == "chat"

    def test_two_lines_over_80_chars(self):
        """Only 2 newlines — does not meet the >=3 newline threshold."""
        text = "a" * 40 + "\n" + "b" * 40 + "\n" + "c" * 10
        assert text.count("\n") == 2
        assert len(text) >= 80
        # Not 180+ chars, not 3+ newlines -> chat
        assert _type(text) == "chat"

    def test_exactly_at_multiline_boundary(self):
        """Exactly 3 newlines (interior) and stripped length >= 80 chars."""
        # strip() removes trailing whitespace/newlines, so newlines must be interior.
        # 4 segments of 20 chars each = 80 chars content + 3 newlines = 83 total
        # After strip: 83 chars, 3 newlines
        text = "x" * 20 + "\n" + "y" * 20 + "\n" + "z" * 20 + "\n" + "w" * 20
        assert len(text.strip()) == 83
        assert text.strip().count("\n") == 3
        assert _type(text) == "analyze_text"


# ── 7. Short text → chat ────────────────────────────────────────────────────


class TestShortText:
    def test_simple_question(self):
        assert _type("这个产品怎么样") == "chat"

    def test_english_sentence(self):
        assert _type("What do you think about this?") == "chat"

    def test_single_word(self):
        assert _type("interesting") == "chat"

    def test_greeting(self):
        """Greetings are not special-cased at the intent level — they go to chat."""
        # Note: _GREETINGS is defined but not checked in parse_intent as of current code
        assert _type("hello") == "chat"


# ── 8. Retry keywords ───────────────────────────────────────────────────────


class TestRetry:
    def test_retry_english(self):
        assert _type("retry") == "retry"

    def test_again(self):
        assert _type("again") == "retry"


class TestExportCommand:
    def test_slash_export(self):
        intent = parse_intent("/export")
        assert intent.type == "export_markdown"

    def test_slash_export_md_alias(self):
        intent = parse_intent("/export-md")
        assert intent.type == "export_markdown"

    def test_redo(self):
        assert _type("redo") == "retry"

    def test_chinese_retry(self):
        assert _type("再来一次") == "retry"

    def test_chinese_reanalyze(self):
        assert _type("重新分析") == "retry"

    def test_retry_case_insensitive(self):
        assert _type("Retry") == "retry"
        assert _type("RETRY") == "retry"

    def test_retry_with_extra_text_is_chat(self):
        """'retry please' is not a bare retry keyword — falls to chat."""
        assert _type("retry please") != "retry"


# ── 9. Provider switching ───────────────────────────────────────────────────


class TestSwitchProvider:
    def test_chinese_use(self):
        i = parse_intent("用 deepseek")
        assert i.type == "switch_provider"
        assert i.provider == "deepseek"

    def test_chinese_switch(self):
        i = parse_intent("切换 openai")
        assert i.type == "switch_provider"
        assert i.provider == "openai"

    def test_english_use(self):
        i = parse_intent("use anthropic")
        assert i.type == "switch_provider"
        assert i.provider == "anthropic"

    def test_switch_to(self):
        i = parse_intent("switch to gemini")
        assert i.type == "switch_provider"
        assert i.provider == "gemini"

    def test_invalid_provider_not_matched(self):
        """A provider name not in PROVIDERS should not match switch_provider."""
        i = parse_intent("用 fakemodel")
        assert i.type != "switch_provider"

    def test_case_insensitive(self):
        i = parse_intent("Use DeepSeek")
        assert i.type == "switch_provider"
        assert i.provider == "deepseek"


# ── 10. Model switching ─────────────────────────────────────────────────────


class TestSwitchModel:
    def test_slash_model_with_arg(self):
        i = parse_intent("/model gpt-4o")
        assert i.type == "switch_model"
        assert i.model == "gpt-4o"

    def test_slash_model_no_arg(self):
        i = parse_intent("/model")
        assert i.type == "switch_model"
        assert i.model == ""


# ── 11. Vote ────────────────────────────────────────────────────────────────


class TestVote:
    def test_chinese_vote(self):
        i = parse_intent("投票 deepseek,openai")
        assert i.type == "vote"
        assert "deepseek" in i.providers
        assert "openai" in i.providers

    def test_english_vote(self):
        i = parse_intent("vote deepseek,anthropic,gemini")
        assert i.type == "vote"
        assert len(i.providers) == 3

    def test_vote_space_separated(self):
        i = parse_intent("vote deepseek openai")
        assert i.type == "vote"
        assert len(i.providers) == 2

    def test_vote_single_provider_not_enough(self):
        """Vote requires at least 2 valid providers."""
        i = parse_intent("投票 deepseek")
        assert i.type != "vote"

    def test_slash_vote(self):
        i = parse_intent("/vote deepseek,openai")
        assert i.type == "vote"
        assert len(i.providers) == 2

    def test_slash_vote_no_args(self):
        i = parse_intent("/vote")
        assert i.type == "unclear"


# ── 12. Slash commands ──────────────────────────────────────────────────────


class TestSlashCommands:
    def test_help(self):
        assert _type("/help") == "help"

    def test_help_alias(self):
        assert _type("/h") == "help"

    def test_exit(self):
        assert _type("/exit") == "exit"

    def test_quit(self):
        assert _type("/quit") == "exit"

    def test_q(self):
        assert _type("/q") == "exit"

    def test_clear(self):
        assert _type("/clear") == "clear_screen"

    def test_history(self):
        assert _type("/history") == "show_history"

    def test_config(self):
        assert _type("/config") == "show_config"

    def test_theme(self):
        assert _type("/theme") == "switch_theme"

    def test_provider_no_arg(self):
        i = parse_intent("/provider")
        assert i.type == "switch_provider"
        assert i.provider == ""

    def test_provider_with_arg(self):
        i = parse_intent("/provider deepseek")
        assert i.type == "switch_provider"
        assert i.provider == "deepseek"

    def test_lang(self):
        i = parse_intent("/lang zh")
        assert i.type == "switch_lang"
        assert i.lang == "zh"

    def test_unknown_slash_command(self):
        assert _type("/foobar") == "unknown_command"


# ── 13. Exit keywords ───────────────────────────────────────────────────────


class TestExit:
    def test_exit(self):
        assert _type("exit") == "exit"

    def test_quit(self):
        assert _type("quit") == "exit"

    def test_q(self):
        assert _type("q") == "exit"

    def test_chinese_exit(self):
        assert _type("退出") == "exit"

    def test_exit_case_insensitive(self):
        assert _type("Exit") == "exit"
        assert _type("QUIT") == "exit"


# ── 14. Help keywords ───────────────────────────────────────────────────────


class TestHelp:
    def test_help(self):
        assert _type("help") == "help"

    def test_question_mark(self):
        assert _type("?") == "help"

    def test_chinese_help(self):
        assert _type("帮助") == "help"


# ── 15. Empty input ─────────────────────────────────────────────────────────


class TestEmptyInput:
    def test_empty_string(self):
        # Empty input: _clean_path("") resolves to cwd, which is a directory.
        # So the result is analyze_batch (if cwd has .md/.txt/.pdf) or unclear.
        i = parse_intent("")
        assert i.type in ("analyze_batch", "unclear")

    def test_whitespace_only(self):
        # Same as empty — stripped to "", resolves to cwd directory.
        i = parse_intent("   ")
        assert i.type in ("analyze_batch", "unclear")


# ── 16. Edge cases / boundary conditions ────────────────────────────────────


class TestEdgeCases:
    def test_intent_preserves_raw(self):
        raw = "  https://github.com/user/repo  "
        i = parse_intent(raw)
        assert i.raw == raw

    def test_url_takes_priority_over_long_text(self):
        """Even if input is 180+ chars, a URL should be detected first."""
        padding = "a" * 200
        text = f"{padding} https://github.com/user/repo"
        i = parse_intent(text)
        assert i.type == "analyze_github"

    def test_url_takes_priority_over_retry(self):
        text = "retry https://example.com"
        i = parse_intent(text)
        assert i.type == "analyze_web"

    def test_exit_checked_before_provider_switch(self):
        """'exit' matches exit keywords before provider regex could match."""
        assert _type("exit") == "exit"

    def test_slash_with_file_path(self, tmp_path):
        """Paths starting with / should not be confused with slash commands."""
        f = tmp_path / "notes.md"
        f.write_text("notes")
        i = parse_intent(str(f))
        assert i.type == "analyze_file"

    def test_text_at_179_chars_is_chat(self):
        assert _type("x" * 179) == "chat"

    def test_text_at_180_chars_is_analyze(self):
        assert _type("x" * 180) == "analyze_text"

    def test_text_at_181_chars_is_analyze(self):
        assert _type("x" * 181) == "analyze_text"

    def test_multiline_at_below_80_chars_is_chat(self):
        """3 interior newlines but stripped length < 80 chars — should be chat."""
        # 18 + 1 + 18 + 1 + 18 + 1 + 18 = 75 chars, 3 newlines
        text = "a" * 18 + "\n" + "b" * 18 + "\n" + "c" * 18 + "\n" + "d" * 18
        assert text.strip().count("\n") == 3
        assert len(text.strip()) == 75
        assert _type(text) == "chat"

    def test_multiline_at_80_chars_is_analyze(self):
        # Newlines must be interior (strip() removes trailing ones).
        # 20 + 1 + 20 + 1 + 20 + 1 + 20 = 83 chars after strip, 3 newlines
        text = "a" * 20 + "\n" + "b" * 20 + "\n" + "c" * 20 + "\n" + "d" * 20
        assert text.strip().count("\n") == 3
        assert len(text.strip()) >= 80
        assert _type(text) == "analyze_text"

    def test_backslash_space_in_path(self, tmp_path):
        """macOS drag-and-drop style escaped spaces should be handled."""
        d = tmp_path / "my dir"
        d.mkdir()
        f = d / "file.md"
        f.write_text("test")
        # Simulate: /path/to/my\ dir/file.md
        escaped = str(f).replace(" ", "\\ ")
        i = parse_intent(escaped)
        assert i.type == "analyze_file"

    def test_tilde_expansion(self):
        """~ should be expanded to home directory."""
        # We can't guarantee a specific file exists, but _clean_path
        # should at least expand the tilde. If ~/.zshrc exists, test it.
        home = os.path.expanduser("~")
        zshrc = os.path.join(home, ".zshrc")
        if os.path.isfile(zshrc):
            i = parse_intent("~/.zshrc")
            assert i.type == "analyze_file"
            assert "~" not in i.path  # tilde should be expanded
