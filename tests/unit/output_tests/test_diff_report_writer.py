from datetime import date, datetime, timezone

from output.diffReportWriter import DiffReportWriter
from scheduling.scheduleDiffService import ScheduleDiffService
from scheduling.scheduleSnapshot import ScheduleSnapshot

from tests.unit.scheduling_tests._part4_helpers import make_exam, make_system


def _snapshot(name, schedule, quality_tag=None, penalty_score=None):
    return ScheduleSnapshot(
        name=name,
        schedule=schedule,
        metrics=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        quality_tag=quality_tag,
        penalty_score=penalty_score,
    )


def test_diff_report_writer_outputs_changed_courses() -> None:
    first = make_system(make_exam("83001", date(2026, 1, 1), name="Algorithms"))
    second = make_system(make_exam("83001", date(2026, 1, 5), name="Algorithms"))
    comparison = ScheduleDiffService().compare(
        _snapshot("A", first),
        _snapshot("B", second),
    )

    text = DiffReportWriter().write_text(comparison)

    assert "From: A" in text
    assert "To:   B" in text
    assert "83001     Algorithms               moved     2026-01-01  2026-01-05" in text
    assert "Quality:" not in text
    assert "Penalty score:" not in text


def test_diff_report_writer_can_write_file(tmp_path) -> None:
    comparison = ScheduleDiffService().compare(
        _snapshot("A", make_system()),
        _snapshot("B", make_system()),
    )
    output_path = tmp_path / "diff_report.txt"

    written_path = DiffReportWriter().write_file(comparison, output_path)

    assert written_path == output_path
    assert "No course date changes" in output_path.read_text(encoding="utf-8")


def test_diff_report_writer_with_metrics_in_both_snapshots() -> None:
    first = _snapshot("A", make_system(), quality_tag="good", penalty_score=100.5)
    second = _snapshot("B", make_system(), quality_tag="better", penalty_score=95.0)

    comparison = ScheduleDiffService().compare(first, second)
    text = DiffReportWriter().write_text(comparison, first, second)

    assert "Quality:" in text
    assert "  A: good" in text
    assert "  B: better" in text
    assert "Penalty score:" in text
    assert "  A: 100.5" in text
    assert "  B: 95" in text
    assert "Penalty score delta" in text
    assert "-5.5" in text


def test_diff_report_writer_missing_quality_tag_on_one_side() -> None:
    first = _snapshot("A", make_system(), quality_tag=None)
    second = _snapshot("B", make_system(), quality_tag="awesome")

    comparison = ScheduleDiffService().compare(first, second)
    text = DiffReportWriter().write_text(comparison, first, second)

    assert "  A: n/a" in text
    assert "  B: awesome" in text


def test_diff_report_writer_missing_penalty_scores() -> None:
    first = _snapshot("A", make_system(), penalty_score=None)
    second = _snapshot("B", make_system(), penalty_score=None)

    comparison = ScheduleDiffService().compare(first, second)
    text = DiffReportWriter().write_text(comparison, first, second)

    assert "  A: n/a" in text
    assert "  B: n/a" in text
    assert "Penalty score delta" in text
    assert "n/a" in text


def test_diff_report_writer_course_added() -> None:
    first = make_system()
    second = make_system(make_exam("83002", date(2026, 2, 10), name="Calculus"))

    comparison = ScheduleDiffService().compare(_snapshot("A", first), _snapshot("B", second))
    text = DiffReportWriter().write_text(comparison)

    assert "83002     Calculus                 added     -           2026-02-10" in text


def test_diff_report_writer_course_removed() -> None:
    first = make_system(make_exam("83003", date(2026, 3, 15), name="Physics"))
    second = make_system()

    comparison = ScheduleDiffService().compare(_snapshot("A", first), _snapshot("B", second))
    text = DiffReportWriter().write_text(comparison)

    assert "83003     Physics                  removed   2026-03-15  -" in text


def test_diff_report_writer_multiple_courses_alignment() -> None:
    first = make_system(
        make_exam("83001", date(2026, 1, 1), name="Algorithms"),
        make_exam("83003", date(2026, 3, 15), name="Physics"),
    )
    second = make_system(
        make_exam("83001", date(2026, 1, 5), name="Algorithms"),
        make_exam("83002", date(2026, 2, 10), name="Calculus"),
    )

    comparison = ScheduleDiffService().compare(_snapshot("A", first), _snapshot("B", second))
    text = DiffReportWriter().write_text(comparison)

    lines = text.splitlines()
    assert "--------- -----------              ------    ----        --" in text

    assert "83001     Algorithms               moved     2026-01-01  2026-01-05" in lines
    assert "83002     Calculus                 added     -           2026-02-10" in lines
    assert "83003     Physics                  removed   2026-03-15  -" in lines

