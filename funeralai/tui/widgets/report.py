"""Report display widgets for the TUI.

Renders analysis results with Rich renderables so Textual can wrap content
correctly in narrow terminals.
"""

from __future__ import annotations

from textual.widgets import Static


class ReportView(Static):
    """Renders a single analysis result."""

    def __init__(
        self,
        result: dict,
        inspection: dict | None = None,
        input_type: str = "local",
        **kwargs,
    ):
        super().__init__("", markup=False, **kwargs)
        self._result = result
        self._inspection = inspection
        self._input_type = input_type

    def on_mount(self) -> None:
        self.update(self._build_content())

    def _build_content(self):
        from funeralai.output import render_batch_report, render_report

        if isinstance(self._result, list):
            return render_batch_report(self._result)
        return render_report(self._result, self._inspection, self._input_type)


class VoteReportView(Static):
    """Renders multi-model vote result."""

    def __init__(
        self,
        vote_result: dict,
        inspection: dict | None = None,
        input_type: str = "local",
        **kwargs,
    ):
        super().__init__("", markup=False, **kwargs)
        self._vote_result = vote_result
        self._inspection = inspection
        self._input_type = input_type

    def on_mount(self) -> None:
        self.update(self._build_content())

    def _build_content(self):
        from funeralai.output import render_vote_report

        return render_vote_report(
            self._vote_result,
            self._inspection,
            self._input_type,
        )


class ChatMessageView(Static):
    """Renders a plain-text chat reply from the assistant."""

    def __init__(self, reply: str, **kwargs):
        super().__init__("", markup=False, **kwargs)
        self._reply = reply

    def on_mount(self) -> None:
        self.update(f"assistant: {self._reply}")


class StatusMessage(Static):
    """Simple styled status/info line."""

    def __init__(self, text: str, style: str = "dim", **kwargs):
        super().__init__("", markup=False, **kwargs)
        self._msg_text = text
        self._msg_style = style

    def on_mount(self) -> None:
        from rich.text import Text

        self.update(Text(self._msg_text, style=self._msg_style))
