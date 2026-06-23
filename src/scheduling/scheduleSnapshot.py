from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ranking_settings import ScheduleMetrics
from scheduling.examScheduleGenerator import ExamSystem


@dataclass(frozen=True)
class ScheduleSnapshot:
    """A named in-memory copy of one schedule version."""

    name: str
    schedule: ExamSystem
    metrics: ScheduleMetrics | None
    created_at: datetime
    quality_tag: str | None = None
    penalty_score: float | None = None


class SnapshotManager:
    """Stores named schedule snapshots for the current session."""

    def __init__(self) -> None:
        self._snapshots: dict[str, ScheduleSnapshot] = {}
        self._active_schedule: ExamSystem | None = None
        self._active_metrics: ScheduleMetrics | None = None

    @property
    def active_schedule(self) -> ExamSystem | None:
        """Return the active schedule copy, if one was loaded or set."""
        return deepcopy(self._active_schedule)

    @property
    def active_metrics(self) -> ScheduleMetrics | None:
        """Return the active metrics copy, if present."""
        return deepcopy(self._active_metrics)

    def set_active_schedule(
        self,
        schedule: ExamSystem,
        metrics: ScheduleMetrics | None = None,
    ) -> None:
        """Set the schedule that snapshot operations work on."""
        self._active_schedule = deepcopy(schedule)
        self._active_metrics = deepcopy(metrics)

    def save_current(
        self,
        name: str,
        *,
        quality_tag: str | None = None,
        penalty_score: float | None = None,
        created_at: datetime | None = None,
    ) -> ScheduleSnapshot:
        """Save the active schedule under a unique non-empty name."""
        if self._active_schedule is None:
            raise ValueError("No active schedule is available to save.")

        return self.save(
            name,
            self._active_schedule,
            metrics=self._active_metrics,
            quality_tag=quality_tag,
            penalty_score=penalty_score,
            created_at=created_at,
        )

    def save(
        self,
        name: str,
        schedule: ExamSystem,
        *,
        metrics: ScheduleMetrics | None = None,
        quality_tag: str | None = None,
        penalty_score: float | None = None,
        created_at: datetime | None = None,
    ) -> ScheduleSnapshot:
        """Create a new snapshot without changing exported files."""
        clean_name = self._validate_new_name(name)
        snapshot = ScheduleSnapshot(
            name=clean_name,
            schedule=deepcopy(schedule),
            metrics=deepcopy(metrics),
            created_at=created_at or datetime.now(timezone.utc),
            quality_tag=quality_tag,
            penalty_score=penalty_score,
        )
        self._snapshots[clean_name] = snapshot
        return self._copy_snapshot(snapshot)

    def load(self, name: str) -> ScheduleSnapshot:
        """Load a snapshot and make it the active schedule."""
        snapshot = self._snapshot_by_name(name)
        self._active_schedule = deepcopy(snapshot.schedule)
        self._active_metrics = deepcopy(snapshot.metrics)
        return self._copy_snapshot(snapshot)

    def rename(self, old_name: str, new_name: str) -> ScheduleSnapshot:
        """Rename a saved snapshot while keeping its schedule copy."""
        snapshot = self._snapshot_by_name(old_name)
        clean_new_name = self._validate_new_name(new_name)

        del self._snapshots[snapshot.name]
        renamed = replace(snapshot, name=clean_new_name)
        self._snapshots[clean_new_name] = renamed
        return self._copy_snapshot(renamed)

    def delete(self, name: str) -> None:
        """Delete one saved snapshot from the current session."""
        snapshot = self._snapshot_by_name(name)
        del self._snapshots[snapshot.name]

    def list_snapshots(self) -> list[ScheduleSnapshot]:
        """Return saved snapshots ordered by creation time then name."""
        return [
            self._copy_snapshot(snapshot)
            for snapshot in sorted(
                self._snapshots.values(),
                key=lambda item: (item.created_at, item.name),
            )
        ]

    def _validate_new_name(self, name: str) -> str:
        clean_name = name.strip()

        if not clean_name:
            raise ValueError("Snapshot name cannot be empty.")

        if clean_name in self._snapshots:
            raise ValueError(f"Snapshot name already exists: {clean_name}.")

        return clean_name

    def _snapshot_by_name(self, name: str) -> ScheduleSnapshot:
        clean_name = name.strip()

        try:
            return self._snapshots[clean_name]
        except KeyError as error:
            raise KeyError(f"Snapshot was not found: {clean_name}.") from error

    @staticmethod
    def _copy_snapshot(snapshot: ScheduleSnapshot) -> ScheduleSnapshot:
        return ScheduleSnapshot(
            name=snapshot.name,
            schedule=deepcopy(snapshot.schedule),
            metrics=deepcopy(snapshot.metrics),
            created_at=snapshot.created_at,
            quality_tag=snapshot.quality_tag,
            penalty_score=snapshot.penalty_score,
        )
