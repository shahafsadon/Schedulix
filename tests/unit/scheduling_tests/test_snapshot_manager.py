from datetime import date, datetime, timezone

import pytest

from scheduling.scheduleIntrospection import flatten_exam_system
from scheduling.scheduleSnapshot import SnapshotManager

from ._part4_helpers import make_exam, make_metrics, make_system


def test_save_and_load_named_snapshot_updates_active_schedule() -> None:
    manager = SnapshotManager()
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))
    metrics = make_metrics()

    manager.set_active_schedule(schedule, metrics)
    saved = manager.save_current(
        "base",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    loaded = manager.load("base")

    assert saved.name == "base"
    assert loaded.name == "base"
    assert flatten_exam_system(manager.active_schedule)[0].exam_date == date(2026, 1, 1)
    assert manager.active_metrics == metrics


def test_empty_and_duplicate_snapshot_names_are_rejected() -> None:
    manager = SnapshotManager()
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))

    with pytest.raises(ValueError, match="empty"):
        manager.save("", schedule)

    manager.save("base", schedule)
    with pytest.raises(ValueError, match="already exists"):
        manager.save(" base ", schedule)


def test_saved_snapshot_is_independent_from_later_active_changes() -> None:
    manager = SnapshotManager()
    original = make_system(make_exam("83001", date(2026, 1, 1)))
    changed = make_system(make_exam("83001", date(2026, 1, 9)))

    manager.set_active_schedule(original)
    manager.save_current("before move")
    manager.set_active_schedule(changed)

    manager.load("before move")

    assert flatten_exam_system(manager.active_schedule)[0].exam_date == date(2026, 1, 1)


def test_delete_and_rename_snapshot_update_the_session_list() -> None:
    manager = SnapshotManager()
    schedule = make_system(make_exam("83001", date(2026, 1, 1)))

    manager.save("old", schedule)
    renamed = manager.rename("old", "new")

    assert renamed.name == "new"
    assert [snapshot.name for snapshot in manager.list_snapshots()] == ["new"]

    manager.delete("new")

    assert manager.list_snapshots() == []
