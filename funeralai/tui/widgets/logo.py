"""Brand ANSI art logo widget."""

import os
from pathlib import Path

from rich.text import Text
from textual.widgets import Static

_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "cli_assets"

# Pure-black foreground escape — invisible on dark terminal backgrounds.
_BLACK_FG = "\x1b[38;2;0;0;0m"


class Logo(Static):
    """Brand ANSI art logo widget."""

    def __init__(self, first_run: bool = False, **kwargs):
        self._first_run = first_run
        # Initialize with placeholder; real content set on mount
        super().__init__("", **kwargs)

    def on_mount(self):
        self.update(self._render_logo())

    def on_resize(self):
        self.update(self._render_logo())

    def refresh_logo(self) -> None:
        """Re-render the logo (e.g. after a theme switch)."""
        self.update(self._render_logo())

    # -- internals -------------------------------------------------------------

    def _theme_text_rgb(self) -> tuple[int, int, int]:
        """Return (r, g, b) for the current theme's text color.

        Falls back to a light grey if the theme object is unavailable.
        """
        try:
            hex_color = self.app.theme_obj.colors.text  # e.g. "#E0E0E0"
        except Exception:
            hex_color = "#E0E0E0"

        hex_color = hex_color.lstrip("#")
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )

    def _render_logo(self):
        width = self.app.size.width if self.app else 80
        height = self.app.size.height if self.app else 24

        # First run shows big banner; subsequent runs show compact icon.
        # Even on first run, fall back to icon if terminal is too short.
        use_banner = self._first_run and height >= 20

        if use_banner:
            # First run: big banner
            if width >= 110:
                art = self._load("banner/large.ansi.txt")
            elif width >= 80:
                art = self._load("banner/small.ansi.txt")
            else:
                art = self._load("icon/small.ansi.txt")
        else:
            # Subsequent runs: compact icon
            if width >= 80:
                art = self._load("icon/large.ansi.txt")
            else:
                art = self._load("icon/small.ansi.txt")

        if art:
            # Replace pure-black foreground with the theme's text color so
            # the banner remains visible on dark backgrounds.
            r, g, b = self._theme_text_rgb()
            art = art.replace(_BLACK_FG, f"\x1b[38;2;{r};{g};{b}m")
            return Text.from_ansi(art)
        else:
            return "葬AI"

    @staticmethod
    def _load(relative: str) -> str | None:
        try:
            return (_ASSETS_DIR / relative).read_text("utf-8")
        except Exception:
            return None

    @staticmethod
    def _supports_truecolor() -> bool:
        return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
