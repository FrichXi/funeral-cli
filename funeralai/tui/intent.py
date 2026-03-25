"""Intent parsing — pure rules, NO LLM.

Classifies a single line of user input into an ``Intent`` for dispatch.
Extracted from the old session.py to be usable as standalone pure functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Intent dataclass
# ---------------------------------------------------------------------------


@dataclass
class Intent:
    """Parsed user intent from a single line of input."""

    type: str  # e.g. "analyze_github", "switch_provider", "exit", ...
    raw: str = ""
    url: str = ""
    path: str = ""
    paths: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    lang: str = ""
    text: str = ""


# ---------------------------------------------------------------------------
# Slash commands recognized after "/"
# ---------------------------------------------------------------------------

_SLASH_COMMANDS = {
    "help", "h",
    "provider",
    "model",
    "vote",
    "export",
    "export-md",
    "lang",
    "history",
    "config",
    "clear",
    "exit", "quit", "q",
    "theme",
}

# ---------------------------------------------------------------------------
# URL / path patterns
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"(https?://\S+)")
_GITHUB_RE = re.compile(r"https?://github\.com/[^/]+/[^/]+")

# Provider switching patterns (Chinese + English)
_SWITCH_PROVIDER_RE = re.compile(
    r"^(?:用|使用|切换到?|use|switch\s+to)\s+(\S+)$",
    re.IGNORECASE,
)

# Vote patterns: "投票 a,b,c" or "/vote a,b,c" or "vote a,b,c"
_VOTE_RE = re.compile(
    r"^(?:投票|vote)\s+([\w,\s]+)$",
    re.IGNORECASE,
)

# Retry keywords
_RETRY_WORDS = {"再来一次", "重新分析", "retry", "again", "redo"}

# Exit keywords
_EXIT_WORDS = {"exit", "quit", "q", "退出"}

# Help keywords
_HELP_WORDS = {"help", "?", "帮助"}

# Greetings — treated as "unclear" with a friendly reply
_GREETINGS = {"你好", "hi", "hello", "hey"}

# Supported file extensions for batch expansion
_BATCH_EXTS = {".md", ".txt", ".pdf"}


# ---------------------------------------------------------------------------
# Path cleaning
# ---------------------------------------------------------------------------


def _clean_path(s: str) -> str:
    """Normalize a user-typed path: strip quotes, unescape spaces, expand ~."""
    s = s.strip()
    # Strip surrounding quotes
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        s = s[1:-1]
    # Unescape backslash-space (common in macOS drag-and-drop)
    s = s.replace("\\ ", " ")
    # Expand ~ and resolve
    return str(Path(s).expanduser().resolve())


# ---------------------------------------------------------------------------
# Provider model lists (hardcoded — APIs don't expose model catalogs)
# ---------------------------------------------------------------------------

_PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-sonnet-4-6",
        "claude-opus-4-20250514",
        "claude-haiku-4-20250514",
    ],
    "openai": ["gpt-5.4-mini", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "gemini": ["gemini-3.1-pro-preview", "gemini-2.0-flash"],
    "qwen": ["qwen-plus", "qwen-max", "qwen-turbo"],
    "kimi": ["kimi-k2.5", "moonshot-v1-128k"],
    "minimax": ["MiniMax-M2.7", "MiniMax-Text-01"],
    "zhipu": ["glm-4.7", "glm-4-flash", "glm-4-long"],
}


# ---------------------------------------------------------------------------
# Intent parsing — pure rules, NO LLM
# ---------------------------------------------------------------------------


def parse_intent(raw: str, last_input_type: str | None = None) -> Intent:  # noqa: C901
    """Classify a single line of user input into an ``Intent``."""
    stripped = raw.strip()
    lower = stripped.lower()

    # 1. Slash commands (but NOT file paths like /Users/...)
    if stripped.startswith("/"):
        word = stripped[1:].split()[0].lower() if len(stripped) > 1 else ""
        if word in _SLASH_COMMANDS:
            return _parse_slash(word, stripped)
        # If it doesn't look like a file path, treat as unknown command.
        # File paths contain "/" after the leading one (e.g. /Users/x/f.md).
        elif "/" not in stripped[1:] and not Path(stripped).expanduser().exists():
            return Intent(type="unknown_command", raw=raw)

    # 2. Exit
    if lower in _EXIT_WORDS:
        return Intent(type="exit", raw=raw)

    # 3. Help
    if lower in _HELP_WORDS:
        return Intent(type="help", raw=raw)

    # 4. URL
    url_match = _URL_RE.search(stripped)
    if url_match:
        url = url_match.group(1).rstrip(".,;")
        if _GITHUB_RE.match(url):
            return Intent(type="analyze_github", raw=raw, url=url)
        return Intent(type="analyze_web", raw=raw, url=url)

    # 5. Directory path -> batch
    cleaned = _clean_path(stripped)
    p = Path(cleaned)
    if p.is_dir():
        files = sorted(
            str(f)
            for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in _BATCH_EXTS
        )
        if files:
            return Intent(
                type="analyze_batch", raw=raw, path=cleaned, paths=files
            )
        # Empty directory or no supported files — treat as unclear
        return Intent(type="unclear", raw=raw)

    # 6. File path
    if p.is_file():
        return Intent(type="analyze_file", raw=raw, path=cleaned)

    # Also try the raw string (before cleaning) for relative paths
    raw_p = Path(stripped).expanduser()
    if raw_p.is_file():
        return Intent(
            type="analyze_file", raw=raw, path=str(raw_p.resolve())
        )

    # 7. Provider switching: "用 deepseek" / "use openai"
    switch_match = _SWITCH_PROVIDER_RE.match(stripped)
    if switch_match:
        name = switch_match.group(1).lower()
        from funeralai.analyzer import PROVIDERS

        if name in PROVIDERS:
            return Intent(type="switch_provider", raw=raw, provider=name)

    # 8. Vote: "投票 deepseek,openai" / "vote a,b,c"
    vote_match = _VOTE_RE.match(stripped)
    if vote_match:
        names = [
            n.strip().lower()
            for n in re.split(r"[,\s]+", vote_match.group(1))
            if n.strip()
        ]
        from funeralai.analyzer import PROVIDERS

        valid = [n for n in names if n in PROVIDERS]
        if len(valid) >= 2:
            return Intent(type="vote", raw=raw, providers=valid)

    # 9. Retry
    if lower in _RETRY_WORDS:
        return Intent(type="retry", raw=raw)

    # 10. Long text -> analyze as local material
    # 180+ chars, or multi-line (>=3 lines) with some substance (>=80 chars)
    if len(stripped) >= 180:
        return Intent(type="analyze_text", raw=raw, text=stripped)
    if stripped.count("\n") >= 3 and len(stripped) >= 80:
        return Intent(type="analyze_text", raw=raw, text=stripped)

    # 11. Chat fallback — send to LLM for natural conversation
    return Intent(type="chat", raw=raw, text=stripped)


# ---------------------------------------------------------------------------
# Slash command sub-parser
# ---------------------------------------------------------------------------


def _parse_slash(cmd: str, full: str) -> Intent:
    """Parse a recognised slash command into an Intent."""
    parts = full.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("help", "h"):
        return Intent(type="help", raw=full)

    if cmd in ("exit", "quit", "q"):
        return Intent(type="exit", raw=full)

    if cmd == "clear":
        return Intent(type="clear_screen", raw=full)

    if cmd == "history":
        return Intent(type="show_history", raw=full)

    if cmd in ("export", "export-md"):
        return Intent(type="export_markdown", raw=full)

    if cmd == "config":
        return Intent(type="show_config", raw=full)

    if cmd == "theme":
        return Intent(type="switch_theme", raw=full)

    if cmd == "provider":
        if arg:
            name = arg.lower()
            from funeralai.analyzer import PROVIDERS

            if name in PROVIDERS:
                return Intent(type="switch_provider", raw=full, provider=name)
        # No arg or invalid provider — still route to handler (it shows usage)
        return Intent(type="switch_provider", raw=full, provider=arg.lower())

    if cmd == "model":
        return Intent(type="switch_model", raw=full, model=arg)

    if cmd == "lang":
        return Intent(type="switch_lang", raw=full, lang=arg.lower())

    if cmd == "vote":
        names = [
            n.strip().lower()
            for n in re.split(r"[,\s]+", arg)
            if n.strip()
        ]
        from funeralai.analyzer import PROVIDERS

        valid = [n for n in names if n in PROVIDERS]
        if len(valid) >= 2:
            return Intent(type="vote", raw=full, providers=valid)
        # Not enough valid providers — treat as unclear
        return Intent(type="unclear", raw=full)

    return Intent(type="unknown_command", raw=full)
