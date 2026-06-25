"""Writes a complete snapshot comparison report including quality/penalty metrics and changed courses."""

from __future__ import annotations

from pathlib import Path

from scheduling.scheduleDiffService import SnapshotComparisonResult
from scheduling.scheduleSnapshot import ScheduleSnapshot


class DiffReportWriter:
    """Writes a readable text report for two compared snapshots."""

    def write_text(
        self,
        result: SnapshotComparisonResult,
        first_snapshot: ScheduleSnapshot | None = None,
        second_snapshot: ScheduleSnapshot | None = None,
    ) -> str:
        """Return the diff report as plain text."""
        lines: list[str] = []

        lines.extend(self._build_header(result))

        if first_snapshot is not None or second_snapshot is not None:
            lines.extend(self._build_metrics(result, first_snapshot, second_snapshot))
            lines.append("")

        lines.extend(self._build_courses(result))
        lines.extend(self._build_footer())

        return "\n".join(lines)

    def write_file(
        self,
        result: SnapshotComparisonResult,
        output_path: str | Path,
        first_snapshot: ScheduleSnapshot | None = None,
        second_snapshot: ScheduleSnapshot | None = None,
    ) -> Path:
        """Write the diff report to disk and return the path."""
        path = Path(output_path)
        path.write_text(
            self.write_text(result, first_snapshot, second_snapshot),
            encoding="utf-8",
        )
        return path

    def _build_header(self, result: SnapshotComparisonResult) -> list[str]:
        """Create the top section of the report."""
        return [
            "Snapshot Comparison Report",
            "=" * 40,
            f"From: {result.first_name}",
            f"To:   {result.second_name}",
            "",
        ]

    def _build_metrics(
        self,
        result: SnapshotComparisonResult,
        first: ScheduleSnapshot | None,
        second: ScheduleSnapshot | None,
    ) -> list[str]:
        """Create the quality and penalty metrics section."""
        lines = [
            "-" * 40,
            "Quality:",
        ]

        first_q = first.quality_tag if first else None
        second_q = second.quality_tag if second else None
        lines.append(f"  {result.first_name}: {first_q if first_q is not None else 'n/a'}")
        lines.append(f"  {result.second_name}: {second_q if second_q is not None else 'n/a'}")

        lines.append("Penalty score:")

        def fmt_p(val: float | None) -> str:
            return f"{val:g}" if val is not None else "n/a"

        first_p = first.penalty_score if first else None
        second_p = second.penalty_score if second else None

        lines.append(f"  {result.first_name}: {fmt_p(first_p)}")
        lines.append(f"  {result.second_name}: {fmt_p(second_p)}")

        lines.append(
            "Penalty score delta (second - first; lower is better): "
            f"{fmt_p(result.penalty_delta)}"
        )

        return lines

    def _build_courses(self, result: SnapshotComparisonResult) -> list[str]:
        """Create the changed courses table section."""
        lines = [
            "-" * 40,
            f"Changed courses: {len(result.changed_courses)} change(s)",
            "",
        ]

        if not result.changed_courses:
            lines.append("No course date changes were found between the two snapshots.")
            return lines

        lines.append(f"{'Course ID':<10}{'Course Name':<25}{'Change':<10}{'From':<12}{'To':<12}".rstrip())
        lines.append(f"{'-'*9:<10}{'-'*11:<25}{'-'*6:<10}{'-'*4:<12}{'-'*2:<12}".rstrip())

        for row in result.changed_courses:
            old_date = row.old_date.isoformat() if row.old_date else "-"
            new_date = row.new_date.isoformat() if row.new_date else "-"
            lines.append(
                f"{row.course_id:<10}{row.course_name:<25}{row.change_type:<10}{old_date:<12}{new_date:<12}".rstrip()
            )

        return lines

    def _build_footer(self) -> list[str]:
        """Create the bottom section of the report."""
        return [
            "",
            "=" * 40,
            "End of report.",
        ]
