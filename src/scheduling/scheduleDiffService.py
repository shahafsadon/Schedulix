"""Compare two saved schedule snapshots.

The service returns only courses that changed between two versions. It does not
change either snapshot and it does not touch the exported schedule file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scheduling.scheduleIntrospection import exam_instance_index
from scheduling.scheduleSnapshot import ScheduleSnapshot


@dataclass(frozen=True)
class ScheduleDiffRow:
    """One course-period exam whose scheduled date changed between snapshots."""

    course_id: str
    course_name: str
    semester: str
    moed: str
    old_date: date | None
    new_date: date | None
    change_type: str


@dataclass(frozen=True)
class SnapshotComparisonResult:
    """Structured comparison result for two saved snapshots."""

    first_name: str
    second_name: str
    changed_courses: list[ScheduleDiffRow]
    penalty_delta: float | None = None


class ScheduleDiffService:
    """Compares two schedule snapshots without changing them."""

    def compare(
        self,
        first: ScheduleSnapshot,
        second: ScheduleSnapshot,
    ) -> SnapshotComparisonResult:
        """Return only course-period exams that were added, removed, or moved."""
        first_index = exam_instance_index(first.schedule)
        second_index = exam_instance_index(second.schedule)
        rows: list[ScheduleDiffRow] = []

        for instance_key in sorted(set(first_index) | set(second_index)):
            first_location = first_index.get(instance_key)
            second_location = second_index.get(instance_key)
            course_id, semester, moed = instance_key

            if first_location is None and second_location is not None:
                rows.append(
                    ScheduleDiffRow(
                        course_id=course_id,
                        course_name=second_location.course_name,
                        semester=semester,
                        moed=moed,
                        old_date=None,
                        new_date=second_location.exam_date,
                        change_type="added",
                    )
                )
                continue

            if first_location is not None and second_location is None:
                rows.append(
                    ScheduleDiffRow(
                        course_id=course_id,
                        course_name=first_location.course_name,
                        semester=semester,
                        moed=moed,
                        old_date=first_location.exam_date,
                        new_date=None,
                        change_type="removed",
                    )
                )
                continue

            if (
                first_location is not None
                and second_location is not None
                and first_location.exam_date != second_location.exam_date
            ):
                rows.append(
                    ScheduleDiffRow(
                        course_id=course_id,
                        course_name=second_location.course_name,
                        semester=semester,
                        moed=moed,
                        old_date=first_location.exam_date,
                        new_date=second_location.exam_date,
                        change_type="moved",
                    )
                )

        return SnapshotComparisonResult(
            first_name=first.name,
            second_name=second.name,
            changed_courses=rows,
            penalty_delta=self._penalty_delta(first, second),
        )

    @staticmethod
    def _penalty_delta(
        first: ScheduleSnapshot,
        second: ScheduleSnapshot,
    ) -> float | None:
        if first.penalty_score is None or second.penalty_score is None:
            return None

        return second.penalty_score - first.penalty_score
