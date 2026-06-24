from datetime import date

from application.commands import ScheduleModificationCommand, UndoRedoManager
from scheduling.scheduleIntrospection import flatten_exam_system

from ._part4_helpers import make_exam, make_system


class ScheduleHolder:
    def __init__(self, schedule):
        self.schedule = schedule

    def get(self):
        return self.schedule

    def set(self, schedule):
        self.schedule = schedule


def _date_of(holder: ScheduleHolder, course_id: str = "83001") -> date:
    for location in flatten_exam_system(holder.schedule):
        if location.course_id == course_id:
            return location.exam_date
    raise AssertionError(f"Course {course_id} was not found.")


def _move(holder: ScheduleHolder, course_id: str, new_date: date):
    return ScheduleModificationCommand(
        holder.get,
        holder.set,
        course_id,
        new_date,
    )


def test_undo_and_redo_manual_move_without_regeneration() -> None:
    holder = ScheduleHolder(make_system(make_exam("83001", date(2026, 1, 1))))
    manager = UndoRedoManager()

    result = manager.execute(_move(holder, "83001", date(2026, 1, 5)))
    undo = manager.undo()
    redo = manager.redo()

    assert result.success
    assert undo.success
    assert redo.success
    assert _date_of(holder) == date(2026, 1, 5)


def test_new_successful_move_clears_redo_history() -> None:
    holder = ScheduleHolder(make_system(make_exam("83001", date(2026, 1, 1))))
    manager = UndoRedoManager()

    manager.execute(_move(holder, "83001", date(2026, 1, 5)))
    manager.undo()
    manager.execute(_move(holder, "83001", date(2026, 1, 7)))

    assert manager.redo_count == 0
    assert not manager.redo().success
    assert _date_of(holder) == date(2026, 1, 7)


def test_history_keeps_only_latest_twenty_moves() -> None:
    holder = ScheduleHolder(make_system(make_exam("83001", date(2026, 1, 1))))
    manager = UndoRedoManager(history_limit=20)

    for day in range(2, 24):
        manager.execute(_move(holder, "83001", date(2026, 1, day)))

    assert manager.undo_count == 20

    for _ in range(20):
        assert manager.undo().success

    assert not manager.undo().success
    assert _date_of(holder) == date(2026, 1, 3)
