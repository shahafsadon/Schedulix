from datetime import date, datetime, timezone

from scheduling.scheduleDiffService import ScheduleDiffService
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.scheduleSnapshot import ScheduleSnapshot

from ._part4_helpers import make_exam, make_system


def _snapshot(name, schedule, penalty=None):
    return ScheduleSnapshot(
        name=name,
        schedule=schedule,
        metrics=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        penalty_score=penalty,
    )


def test_identical_snapshots_return_no_changed_courses() -> None:
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))

    result = ScheduleDiffService().compare(
        _snapshot("A", schedule),
        _snapshot("B", schedule),
    )

    assert result.changed_courses == []


def test_compare_returns_only_moved_added_and_removed_courses() -> None:
    first = make_system(
        make_exam("83001", date(2026, 1, 1), name="Algorithms"),
        make_exam("83002", date(2026, 1, 3), name="Databases"),
    )
    second = make_system(
        make_exam("83001", date(2026, 1, 2), name="Algorithms"),
        make_exam("83003", date(2026, 1, 5), name="Graphics"),
    )

    result = ScheduleDiffService().compare(
        _snapshot("A", first, penalty=20),
        _snapshot("B", second, penalty=35),
    )

    assert [(row.course_id, row.change_type) for row in result.changed_courses] == [
        ("83001", "moved"),
        ("83002", "removed"),
        ("83003", "added"),
    ]
    assert result.changed_courses[0].old_date == date(2026, 1, 1)
    assert result.changed_courses[0].new_date == date(2026, 1, 2)
    assert result.penalty_delta == 15


def test_compare_keeps_aleph_and_bet_entries_for_the_same_course_separate() -> None:
    """Moving Bet must not hide the unchanged Aleph exam in the comparison key."""
    first = ExamSystem(
        period_schedules=[
            ExamSchedule("FALL", "Aleph", [make_exam("83001", date(2026, 1, 1))]),
            ExamSchedule("FALL", "Bet", [make_exam("83001", date(2026, 2, 1))]),
        ]
    )
    second = ExamSystem(
        period_schedules=[
            ExamSchedule("FALL", "Aleph", [make_exam("83001", date(2026, 1, 1))]),
            ExamSchedule("FALL", "Bet", [make_exam("83001", date(2026, 2, 2))]),
        ]
    )

    result = ScheduleDiffService().compare(_snapshot("A", first), _snapshot("B", second))

    assert len(result.changed_courses) == 1
    row = result.changed_courses[0]
    assert (row.course_id, row.semester, row.moed, row.change_type) == (
        "83001",
        "FALL",
        "Bet",
        "moved",
    )
    assert row.old_date == date(2026, 2, 1)
    assert row.new_date == date(2026, 2, 2)
