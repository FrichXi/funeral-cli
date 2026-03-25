"""Animated spinner with phase text."""

from textual.widgets import Static

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class AnalysisSpinner(Static):
    """Animated spinner with phase text."""

    DEFAULT_CSS = """
    AnalysisSpinner {
        height: 1;
    }
    """

    def __init__(self, text: str = "", **kwargs):
        super().__init__("", **kwargs)
        self._text = text
        self._frame = 0
        self._timer = None

    def on_mount(self):
        self._timer = self.set_interval(0.08, self._tick)
        self._do_render()

    def on_unmount(self):
        if self._timer:
            self._timer.stop()

    def _tick(self):
        self._frame = (self._frame + 1) % len(_FRAMES)
        self._do_render()

    def _do_render(self):
        frame_char = _FRAMES[self._frame]
        self.update(f"  [bold magenta]{frame_char}[/] [dim]{self._text}[/]")

    def set_text(self, text: str):
        self._text = text
        self._do_render()
