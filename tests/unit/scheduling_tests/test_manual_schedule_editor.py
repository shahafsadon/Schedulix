from datetime import date

from scheduling.manualScheduleEditor import ManualScheduleEditor
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.scheduleIntrospection import flatten_exam_system

from ._part4_helpers import make_exam, make_system


def test_valid_manual_move_returns_modified_copy_without_mutating_original() -> None:
    original = make_system(make_exam("83001", date(2026, 1, 1)))

    result = ManualScheduleEditor().move_exam(
        original,
        "83001",
        "05-01-2026",
        available_dates={date(2026, 1, 5)},
    )

    assert result.success
    assert flatten_exam_system(result.schedule)[0].exam_date == date(2026, 1, 5)
    assert flatten_exam_system(original)[0].exam_date == date(2026, 1, 1)
    assert result.impact is not None


def test_invalid_course_id_and_invalid_date_are_rejected() -> None:
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))
    editor = ManualScheduleEditor()

    missing = editor.move_exam(schedule, "99999", date(2026, 1, 2))
    invalid_date = editor.move_exam(schedule, "83001", "2026/01/02")

    assert not missing.success
    assert "not found" in missing.message
    assert not invalid_date.success
    assert "Target date" in invalid_date.message


def test_unavailable_date_is_rejected_before_copy_is_committed() -> None:
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))

    result = ManualScheduleEditor().move_exam(
        schedule,
        "83001",
        date(2026, 1, 7),
        available_dates={date(2026, 1, 5)},
    )

    assert not result.success
    assert "not available" in result.message


def test_move_that_creates_critical_conflict_is_rejected() -> None:
    schedule = make_system(
        make_exam("83001", date(2026, 1, 1)),
        make_exam("83002", date(2026, 1, 5)),
    )

    result = ManualScheduleEditor().move_exam(
        schedule,
        "83001",
        date(2026, 1, 5),
    )

    assert not result.success
    assert "critical-conflict" in result.message


def test_move_selects_one_exam_period_when_course_exists_in_aleph_and_bet() -> None:
    """The selected period must move without changing the other course exam."""
    original = ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=[make_exam("83001", date(2026, 1, 1))],
            ),
            ExamSchedule(
                semester="FALL",
                moed="Bet",
                scheduled_exams=[make_exam("83001", date(2026, 2, 1))],
            ),
        ]
    )

    result = ManualScheduleEditor().move_exam(
        original,
        "83001",
        date(2026, 2, 2),
        source_semester="FALL",
        source_moed="Bet",
        source_date=date(2026, 2, 1),
        available_dates={date(2026, 2, 1), date(2026, 2, 2)},
    )

    assert result.success
    moved_dates = {
        (location.semester, location.moed): location.exam_date
        for location in flatten_exam_system(result.schedule)
    }
    original_dates = {
        (location.semester, location.moed): location.exam_date
        for location in flatten_exam_system(original)
    }
    assert moved_dates[("FALL", "Aleph")] == date(2026, 1, 1)
    assert moved_dates[("FALL", "Bet")] == date(2026, 2, 2)
    assert original_dates[("FALL", "Bet")] == date(2026, 2, 1)
