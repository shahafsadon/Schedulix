"""Backward-compatible file location for FileUploadScreen."""

from pathlib import Path


_SOURCE = Path(__file__).with_name("screens") / "fileUploadScreen.py"
exec(compile(_SOURCE.read_text(encoding="utf-8"), str(_SOURCE), "exec"))
