from __future__ import annotations

from pathlib import Path

from scheduling.scheduleDiffService import SnapshotComparisonResult


class DiffReportWriter:
    """Writes a readable text report for two compared snapshots."""

    def write_text(self, result: SnapshotComparisonResult) -> str:
        """Return the diff report as plain text."""
        lines = [
            f"Snapshot comparison: {result.first_name} -> {result.second_name}",
            "",
        ]

        if result.penalty_delta is not None:
            lines.append(f"Penalty delta: {result.penalty_delta:g}")
            lines.append("")

        if not result.changed_courses:
            lines.append("No course date changes were found.")
            return "\n".join(lines)

        lines.append("Changed courses:")
        for row in result.changed_courses:
            old_date = row.old_date.isoformat() if row.old_date else "-"
            new_date = row.new_date.isoformat() if row.new_date else "-"
            lines.append(
                f"- {row.course_id} {row.course_name}: "
                f"{old_date} -> {new_date} ({row.change_type})"
            )

        return "\n".join(lines)

    def write_file(
        self,
        result: SnapshotComparisonResult,
        output_path: str | Path,
    ) -> Path:
        """Write the diff report to disk and return the path."""
        path = Path(output_path)
        path.write_text(self.write_text(result), encoding="utf-8")
        return path
