"""Backward-compatible file location for ScheduleNavigationScreen."""

from pathlib import Path


_SOURCE = Path(__file__).with_name("screens") / "scheduleNavigationScreen.py"
exec(compile(_SOURCE.read_text(encoding="utf-8"), str(_SOURCE), "exec"))
