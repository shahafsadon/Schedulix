"""Backward-compatible file location for DateManagementScreen."""

from pathlib import Path


_SOURCE = Path(__file__).with_name("screens") / "dateManagementScreen.py"
exec(compile(_SOURCE.read_text(encoding="utf-8"), str(_SOURCE), "exec"))
