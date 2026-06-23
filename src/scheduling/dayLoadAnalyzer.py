from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from constraint_settings import SchedulingConstraintSettings, ThresholdConstraintType
from scheduling.examConflictDetector import ExamConflictDetector
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.scheduleIntrospection import flatten_exam_system


class DayStatus(str, Enum):
    """Display-ready status for one calendar day."""

    NORMAL = "normal"
    BUSY = "busy"
    OVERLOADED = "overloaded"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class DayLoadViolation:
    """One reason why a day is problematic."""

    requirement_id: str
    explanation: str


@dataclass(frozen=True)
class DayLoadStatus:
    """The load and status of one scheduled exam date."""

    exam_date: date
    exam_count: int
    status: DayStatus
    violations: list[DayLoadViolation] = field(default_factory=list)


class DayLoadAnalyzer:
    """Finds busy, overloaded, and conflicting dates in a schedule."""

    def __init__(
        self,
        conflict_detector: ExamConflictDetector | None = None,
    ) -> None:
        self._conflict_detector = conflict_detector or ExamConflictDetector()

    def analyze(
        self,
        schedule: ExamSystem,
        settings: SchedulingConstraintSettings | None = None,
    ) -> list[DayLoadStatus]:
        """Return one display status per scheduled date."""
        exams_by_date = self._exams_by_date(schedule)
        conflict_violations = self._conflict_violations(schedule)
        max_exams = self._active_max_exams_per_day(settings)
        statuses: list[DayLoadStatus] = []

        for exam_date in sorted(exams_by_date):
            exam_count = len(exams_by_date[exam_date])
            violations = list(conflict_violations.get(exam_date, []))

            if max_exams is not None and exam_count > max_exams:
                violations.append(
                    DayLoadViolation(
                        requirement_id="Req 2.5",
                        explanation=(
                            f"{exam_count} exams are scheduled on {exam_date}; "
                            f"maximum allowed is {max_exams}."
                        ),
                    )
                )

            statuses.append(
                DayLoadStatus(
                    exam_date=exam_date,
                    exam_count=exam_count,
                    status=self._status_for_day(
                        exam_count=exam_count,
                        has_conflict=exam_date in conflict_violations,
                        is_overloaded=(
                            max_exams is not None and exam_count > max_exams
                        ),
                    ),
                    violations=violations,
                )
            )

        return statuses

    @staticmethod
    def _exams_by_date(schedule: ExamSystem) -> dict[date, list]:
        exams_by_date: dict[date, list] = defaultdict(list)

        for location in flatten_exam_system(schedule):
            exams_by_date[location.exam_date].append(location.exam)

        return exams_by_date

    def _conflict_violations(
        self,
        schedule: ExamSystem,
    ) -> dict[date, list[DayLoadViolation]]:
        violations: dict[date, list[DayLoadViolation]] = defaultdict(list)
        conflicts = self._conflict_detector.find_conflicts(
            [location.exam for location in flatten_exam_system(schedule)]
        )

        for conflict in conflicts:
            violations[conflict.first_exam.exam_date].append(
                DayLoadViolation(
                    requirement_id="V2.0-critical-conflict-rule",
                    explanation=(
                        f"Courses {conflict.first_exam.course.course_number} "
                        f"and {conflict.second_exam.course.course_number} "
                        f"conflict for program {conflict.program_number} "
                        f"year {conflict.year}."
                    ),
                )
            )

        return violations

    @staticmethod
    def _active_max_exams_per_day(
        settings: SchedulingConstraintSettings | None,
    ) -> int | None:
        if settings is None:
            return None

        setting = settings.constraints.get(ThresholdConstraintType.max_exams_per_day)
        if setting is None or not setting.enabled:
            return None

        return setting.k

    @staticmethod
    def _status_for_day(
        *,
        exam_count: int,
        has_conflict: bool,
        is_overloaded: bool,
    ) -> DayStatus:
        if has_conflict:
            return DayStatus.CONFLICT

        if is_overloaded:
            return DayStatus.OVERLOADED

        if exam_count > 1:
            return DayStatus.BUSY

        return DayStatus.NORMAL
