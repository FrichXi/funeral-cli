"""Theme system for the Funeral CLI TUI.

Maps to OpenCode's context/theme.tsx. Loads JSON theme files, detects
terminal dark/light mode, and generates Textual CSS variables.
"""

from __future__ import annotations

import json
import os
import re
import select
import termios
import tty
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Theme color slots (matching OpenCode's semantic color system)
# ---------------------------------------------------------------------------

@dataclass
class ThemeColors:
    """All semantic color slots used by the TUI."""
    primary: str = "#7351CF"
    secondary: str = "#5B3FA0"
    accent: str = "#9B7FE6"
    error: str = "#E55B5B"
    warning: str = "#E5A84B"
    success: str = "#5BE577"
    info: str = "#5B9BE5"
    text: str = "#E0E0E0"
    text_muted: str = "#888888"
    background: str = "#1A1A2E"
    background_panel: str = "#222240"
    background_element: str = "#2A2A4A"
    border: str = "#444466"
    border_active: str = "#7351CF"
    border_subtle: str = "#333355"


# ---------------------------------------------------------------------------
# Theme class
# ---------------------------------------------------------------------------

_THEMES_DIR = Path(__file__).resolve().parent / "themes"
_USER_THEMES_DIR = Path.home() / ".config" / "funeralai" / "themes"

# Built-in theme names (filename without .json)
BUILTIN_THEMES = ("funeral", "catppuccin", "tokyonight", "gruvbox", "nord")
DEFAULT_THEME = "funeral"


class Theme:
    """Manages theme loading and color resolution."""

    def __init__(self, name: str = DEFAULT_THEME, mode: str = "dark"):
        self.name = name
        self.mode = mode  # "dark" or "light"
        self.colors = ThemeColors()
        self._load(name)

    def _load(self, name: str) -> None:
        """Load theme JSON file and populate colors."""
        data = self._read_theme_file(name)
        if data is None:
            return  # keep defaults

        # Resolve defs references
        defs = data.get("defs", {})
        variant = data.get(self.mode, data.get("dark", {}))

        for slot in ThemeColors.__dataclass_fields__:
            raw = variant.get(slot)
            if raw is None:
                continue
            # Resolve $ref syntax: "{defs.purple.500}" -> actual color
            if isinstance(raw, str) and raw.startswith("{") and raw.endswith("}"):
                ref_path = raw[1:-1].split(".")
                resolved = defs
                try:
                    for part in ref_path:
                        resolved = resolved[part]
                    raw = resolved
                except (KeyError, TypeError):
                    continue
            if isinstance(raw, str):
                setattr(self.colors, slot, raw)

    def _read_theme_file(self, name: str) -> dict | None:
        """Find and read theme JSON. User dir takes priority over built-in."""
        for base in (_USER_THEMES_DIR, _THEMES_DIR):
            path = base / f"{name}.json"
            if path.is_file():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
        return None

    def to_css_vars(self) -> str:
        """Generate Textual CSS variable declarations."""
        lines = []
        for slot in ThemeColors.__dataclass_fields__:
            val = getattr(self.colors, slot)
            css_name = slot.replace("_", "-")
            lines.append(f"    --theme-{css_name}: {val};")
        return "\n".join(lines)

    @staticmethod
    def available_themes() -> list[str]:
        """List all available theme names (built-in + user)."""
        names = set(BUILTIN_THEMES)
        if _USER_THEMES_DIR.is_dir():
            for f in _USER_THEMES_DIR.glob("*.json"):
                names.add(f.stem)
        return sorted(names)


# ---------------------------------------------------------------------------
# Terminal background detection (OSC 11)
# ---------------------------------------------------------------------------

def detect_background_mode() -> str:
    """Query terminal for background color via OSC 11.

    Returns "dark" or "light". Falls back to "dark" on any failure.
    Same technique as OpenCode's getTerminalBackgroundColor().
    """
    _mode, _hex = detect_terminal_background()
    return _mode


def detect_terminal_background() -> tuple[str, str | None]:
    """Detect the terminal's actual background color.

    Returns (mode, hex_color) where mode is "dark"/"light" and
    hex_color is the actual background like "#1C1C1E" or None on failure.
    When hex_color is available, it can be used to make Textual's
    background match the terminal exactly (visually "transparent").
    """
    # Check COLORFGBG env var first (simpler, supported by some terminals)
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        parts = colorfgbg.split(";")
        if parts:
            try:
                bg = int(parts[-1])
                return ("light" if bg > 6 else "dark", None)
            except ValueError:
                pass

    tty_path = "/dev/tty"
    if not os.path.exists(tty_path):
        return ("dark", None)

    # Try OSC 11 query against the controlling terminal directly. This is
    # more reliable than sys.stdin/sys.stdout when Textual or a wrapper has
    # already swapped streams around.
    try:
        fd = os.open(tty_path, os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return ("dark", None)

    try:
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            os.write(fd, b"\x1b]11;?\x1b\\")

            response = bytearray()
            if select.select([fd], [], [], 0.15)[0]:
                while True:
                    ready, _, _ = select.select([fd], [], [], 0.03)
                    if not ready:
                        break
                    chunk = os.read(fd, 128)
                    if not chunk:
                        break
                    response.extend(chunk)

            parsed = _parse_osc11_response(response.decode("ascii", errors="ignore"))
            if parsed is not None:
                return parsed
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return ("dark", None)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    return ("dark", None)


_OSC11_RE = re.compile(r"rgb:([0-9A-Fa-f]{1,4})/([0-9A-Fa-f]{1,4})/([0-9A-Fa-f]{1,4})")


def _parse_osc11_response(response: str) -> tuple[str, str] | None:
    """Parse an OSC 11 response into (mode, #rrggbb)."""
    match = _OSC11_RE.search(response)
    if not match:
        return None

    channels = tuple(_normalize_osc_channel(group) for group in match.groups())
    if any(ch is None for ch in channels):
        return None

    ri, gi, bi = channels
    r, g, b = ri / 255, gi / 255, bi / 255
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mode = "light" if luminance > 0.5 else "dark"
    return (mode, f"#{ri:02x}{gi:02x}{bi:02x}")


def _normalize_osc_channel(raw: str) -> int | None:
    """Normalize 1-4 digit OSC channel values to 0-255."""
    try:
        value = int(raw, 16)
    except ValueError:
        return None

    max_value = (16 ** len(raw)) - 1
    if max_value <= 0:
        return None
    return round(value * 255 / max_value)


def get_theme_from_config() -> str:
    """Read theme name from config.json."""
    try:
        from funeralai.config import load_config
        return load_config().get("theme", DEFAULT_THEME)
    except Exception:
        return DEFAULT_THEME


def save_theme_to_config(name: str) -> None:
    """Save theme choice to config.json."""
    from funeralai.config import load_config, save_config
    config = load_config()
    config["theme"] = name
    save_config(config)
