"""Unit tests for the Part 4 schedule services.

These tests cover the backend logic used by the GUI: snapshots, comparison,
day highlighting, manual moves, and undo/redo. They do not open a desktop
window.
"""

from __future__ import annotations

from datetime import date

import pytest

from application.commands import ScheduleModificationCommand, UndoRedoManager
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ProgramEnrollment
from scheduling.dayLoadAnalyzer import DayLoadAnalyzer, DayStatus
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.manualScheduleEditor import ManualScheduleEditor
from scheduling.scheduleDiffService import ScheduleDiffService
from scheduling.scheduleSnapshot import SnapshotManager


def _course(
    course_id: str,
    name: str,
    *,
    program: str = "83101",
    status: str = "Obligatory",
) -> Course:
    """Build one test course."""
    return Course(
        name=name,
        course_number=course_id,
        instructor="Dr. Test",
        programs=[ProgramEnrollment(program, 1, "FALL", status)],
        evaluation_type="Exam",
    )


def _exam(course_id: str, name: str, exam_date: date, **kwargs) -> ScheduledExam:
    """Build one scheduled exam."""
    return ScheduledExam(
        course=_course(course_id, name, **kwargs),
        exam_date=exam_date,
    )


def _system(*exams: ScheduledExam) -> ExamSystem:
    """Build a one-period exam system."""
    return ExamSystem(
        [
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=list(exams),
            )
        ]
    )


def _max_exams_settings(value: int) -> SchedulingConstraintSettings:
    """Build settings with only max_exams_per_day enabled."""
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = (
        ThresholdConstraintSetting(True, value)
    )
    return settings


def test_snapshot_manager_rejects_empty_and_duplicate_names() -> None:
    """Snapshot names must be clear and unique."""
    manager = SnapshotManager()
    manager.set_active_schedule(_system(_exam("83001", "A", date(2026, 1, 1))))

    with pytest.raises(ValueError, match="cannot be empty"):
        manager.save_current("   ")

    manager.save_current("base")
    with pytest.raises(ValueError, match="already exists"):
        manager.save_current("base")


def test_snapshot_load_returns_independent_schedule_copy() -> None:
    """Later active changes must not mutate a saved snapshot."""
    manager = SnapshotManager()
    first = _system(_exam("83001", "A", date(2026, 1, 1)))
    second = _system(_exam("83001", "A", date(2026, 1, 2)))

    manager.set_active_schedule(first)
    manager.save_current("base")
    manager.set_active_schedule(second)

    loaded = manager.load("base")

    assert loaded.schedule.period_schedules[0].scheduled_exams[0].exam_date == date(
        2026,
        1,
        1,
    )


def test_schedule_diff_reports_only_changed_courses() -> None:
    """Snapshot comparison should ignore unchanged courses."""
    manager = SnapshotManager()
    base = manager.save(
        "base",
        _system(
            _exam("83001", "A", date(2026, 1, 1)),
            _exam("83002", "B", date(2026, 1, 3)),
        ),
    )
    moved = manager.save(
        "moved",
        _system(
            _exam("83001", "A", date(2026, 1, 2)),
            _exam("83002", "B", date(2026, 1, 3)),
        ),
    )

    result = ScheduleDiffService().compare(base, moved)

    assert [row.course_id for row in result.changed_courses] == ["83001"]
    assert result.changed_courses[0].old_date == date(2026, 1, 1)
    assert result.changed_courses[0].new_date == date(2026, 1, 2)


def test_day_load_analyzer_distinguishes_overload_and_conflict() -> None:
    """Conflict days should be stronger than normal busy days."""
    overloaded = _system(
        _exam("83001", "A", date(2026, 1, 1), status="Elective"),
        _exam("83002", "B", date(2026, 1, 1), status="Elective"),
    )
    conflict = _system(
        _exam("83001", "A", date(2026, 1, 2)),
        _exam("83002", "B", date(2026, 1, 2)),
    )

    overloaded_status = DayLoadAnalyzer().analyze(
        overloaded,
        _max_exams_settings(1),
    )[0]
    conflict_status = DayLoadAnalyzer().analyze(conflict)[0]

    assert overloaded_status.status == DayStatus.OVERLOADED
    assert conflict_status.status == DayStatus.CONFLICT


def test_manual_schedule_editor_rejects_invalid_and_unavailable_dates() -> None:
    """Invalid user input must not return a modified schedule."""
    schedule = _system(_exam("83001", "A", date(2026, 1, 1)))
    editor = ManualScheduleEditor()

    invalid = editor.move_exam(schedule, "83001", "not-a-date")
    unavailable = editor.move_exam(
        schedule,
        "83001",
        "02-01-2026",
        available_dates={date(2026, 1, 1)},
    )

    assert not invalid.success
    assert invalid.schedule is None
    assert not unavailable.success
    assert unavailable.schedule is None


def test_manual_move_undo_redo_manager_updates_active_schedule() -> None:
    """Undo and redo should not require schedule regeneration."""
    active = {"schedule": _system(_exam("83001", "A", date(2026, 1, 1)))}

    def get_schedule():
        return active["schedule"]

    def set_schedule(schedule):
        active["schedule"] = schedule

    manager = UndoRedoManager()
    command = ScheduleModificationCommand(
        get_schedule,
        set_schedule,
        "83001",
        "02-01-2026",
        available_dates={date(2026, 1, 1), date(2026, 1, 2)},
    )

    assert manager.execute(command).success
    assert active["schedule"].period_schedules[0].scheduled_exams[0].exam_date == date(
        2026,
        1,
        2,
    )

    assert manager.undo().success
    assert active["schedule"].period_schedules[0].scheduled_exams[0].exam_date == date(
        2026,
        1,
        1,
    )

    assert manager.redo().success
    assert active["schedule"].period_schedules[0].scheduled_exams[0].exam_date == date(
        2026,
        1,
        2,
    )
