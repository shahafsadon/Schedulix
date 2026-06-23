from datetime import date, datetime, timezone

from output.diffReportWriter import DiffReportWriter
from scheduling.scheduleDiffService import ScheduleDiffService
from scheduling.scheduleSnapshot import ScheduleSnapshot

from tests.unit.scheduling_tests._part4_helpers import make_exam, make_system


def _snapshot(name, schedule):
    return ScheduleSnapshot(
        name=name,
        schedule=schedule,
        metrics=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_diff_report_writer_outputs_changed_courses() -> None:
    first = make_system(make_exam("83001", date(2026, 1, 1), name="Algorithms"))
    second = make_system(make_exam("83001", date(2026, 1, 5), name="Algorithms"))
    comparison = ScheduleDiffService().compare(
        _snapshot("A", first),
        _snapshot("B", second),
    )

    text = DiffReportWriter().write_text(comparison)

    assert "Snapshot comparison: A -> B" in text
    assert "83001 Algorithms: 2026-01-01 -> 2026-01-05 (moved)" in text


def test_diff_report_writer_can_write_file(tmp_path) -> None:
    comparison = ScheduleDiffService().compare(
        _snapshot("A", make_system()),
        _snapshot("B", make_system()),
    )
    output_path = tmp_path / "diff_report.txt"

    written_path = DiffReportWriter().write_file(comparison, output_path)

    assert written_path == output_path
    assert "No course date changes" in output_path.read_text(encoding="utf-8")
