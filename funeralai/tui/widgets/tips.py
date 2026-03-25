"""Random tip display widget, toggleable."""

import random

from textual.widgets import Static

from funeralai.i18n import TIP_KEYS, t


class Tips(Static):
    """Random tip display widget, toggleable."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._tip_key = random.choice(TIP_KEYS)

    def on_mount(self):
        self.update(self._build_tip())

    def _build_tip(self) -> str:
        tip_text = t(self._tip_key)
        return f"[bold dim]Tip:[/] [dim]{tip_text}[/]"

    def refresh_tip(self):
        """Show a new random tip."""
        self._tip_key = random.choice(TIP_KEYS)
        self.update(self._build_tip())
