"""Markdown export helpers for CLI and TUI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from funeralai.output import (
    format_batch_markdown,
    format_markdown,
    format_markdown_github,
    format_markdown_web,
    format_vote_markdown,
    format_vote_markdown_github,
    format_vote_markdown_web,
    suggest_markdown_basename,
)


def render_markdown(
    result: Any,
    inspection: dict | None = None,
    input_type: str = "local",
) -> str:
    """Render a result or vote result to Markdown."""
    if isinstance(result, list):
        return format_batch_markdown(result)

    if isinstance(result, dict) and result.get("consensus"):
        if input_type == "github" and inspection:
            return format_vote_markdown_github(result, inspection)
        if input_type == "web" and inspection:
            return format_vote_markdown_web(result, inspection)
        return format_vote_markdown(result)

    if input_type == "github" and inspection:
        return format_markdown_github(result, inspection)
    if input_type == "web" and inspection:
        return format_markdown_web(result, inspection)
    return format_markdown(result)


def default_export_path(
    result: Any,
    inspection: dict | None = None,
    input_type: str = "local",
    base_dir: str | Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Build the default output path for a Markdown export."""
    ts = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
    basename = suggest_markdown_basename(result, inspection, input_type)
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "exports"
    return root / f"{ts}_{basename}.md"


def export_markdown(
    result: Any,
    inspection: dict | None = None,
    input_type: str = "local",
    output_path: str | Path | None = None,
    base_dir: str | Path | None = None,
) -> Path:
    """Write Markdown to disk and return the destination path."""
    destination = Path(output_path) if output_path is not None else default_export_path(
        result,
        inspection,
        input_type,
        base_dir=base_dir,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_markdown(result, inspection, input_type),
        encoding="utf-8",
    )
    return destination
