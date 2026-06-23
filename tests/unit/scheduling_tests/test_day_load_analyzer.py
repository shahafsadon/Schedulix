from datetime import date

from scheduling.dayLoadAnalyzer import DayLoadAnalyzer, DayStatus

from ._part4_helpers import make_exam, make_system, max_exams_settings


def test_single_exam_day_is_normal() -> None:
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))

    statuses = DayLoadAnalyzer().analyze(schedule)

    assert statuses[0].status == DayStatus.NORMAL
    assert statuses[0].exam_count == 1


def test_busy_day_is_not_overloaded_without_active_threshold() -> None:
    schedule = make_system(
        make_exam("83001", date(2026, 1, 1), program="83101"),
        make_exam("83002", date(2026, 1, 1), program="83102"),
    )

    statuses = DayLoadAnalyzer().analyze(schedule)

    assert statuses[0].status == DayStatus.BUSY


def test_overloaded_day_uses_active_max_exams_threshold() -> None:
    schedule = make_system(
        make_exam("83001", date(2026, 1, 1), program="83101"),
        make_exam("83002", date(2026, 1, 1), program="83102"),
    )

    statuses = DayLoadAnalyzer().analyze(schedule, max_exams_settings(1))

    assert statuses[0].status == DayStatus.OVERLOADED
    assert statuses[0].violations[0].requirement_id == "Req 2.5"


def test_conflict_day_is_distinguished_from_busy_or_overloaded_day() -> None:
    schedule = make_system(
        make_exam("83001", date(2026, 1, 1)),
        make_exam("83002", date(2026, 1, 1)),
    )

    statuses = DayLoadAnalyzer().analyze(schedule, max_exams_settings(10))

    assert statuses[0].status == DayStatus.CONFLICT
    assert statuses[0].violations[0].requirement_id == "V2.0-critical-conflict-rule"
