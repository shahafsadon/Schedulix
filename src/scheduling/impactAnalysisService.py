from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from constraint_settings import SchedulingConstraintSettings, ThresholdConstraintType
from scheduling.examConflictDetector import ExamConflictDetector
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.scheduleIntrospection import flatten_exam_system


@dataclass(frozen=True)
class ScheduleIssue:
    """One validation issue shown to the user after a manual move."""

    issue_key: tuple[str, ...]
    requirement_id: str
    explanation: str
    course_ids: tuple[str, ...] = ()
    exam_date: date | None = None


@dataclass(frozen=True)
class ImpactAnalysisResult:
    """Shows which issues changed after a manual move."""

    resolved_issues: list[ScheduleIssue]
    new_issues: list[ScheduleIssue]
    unchanged_issues: list[ScheduleIssue]


class ImpactAnalysisService:
    """Compares schedule issues before and after a manual edit."""

    def __init__(
        self,
        conflict_detector: ExamConflictDetector | None = None,
    ) -> None:
        self._conflict_detector = conflict_detector or ExamConflictDetector()

    def analyze(
        self,
        before: ExamSystem,
        after: ExamSystem,
        settings: SchedulingConstraintSettings | None = None,
    ) -> ImpactAnalysisResult:
        """Return resolved, new, and unchanged issues."""
        before_issues = self._issue_map(before, settings)
        after_issues = self._issue_map(after, settings)

        before_keys = set(before_issues)
        after_keys = set(after_issues)

        return ImpactAnalysisResult(
            resolved_issues=self._ordered_values(before_issues, before_keys - after_keys),
            new_issues=self._ordered_values(after_issues, after_keys - before_keys),
            unchanged_issues=self._ordered_values(after_issues, before_keys & after_keys),
        )

    def _issue_map(
        self,
        schedule: ExamSystem,
        settings: SchedulingConstraintSettings | None,
    ) -> dict[tuple[str, ...], ScheduleIssue]:
        issues: dict[tuple[str, ...], ScheduleIssue] = {}
        issues.update(self._critical_conflict_issues(schedule))
        issues.update(self._max_exams_per_day_issues(schedule, settings))
        return issues

    def _critical_conflict_issues(
        self,
        schedule: ExamSystem,
    ) -> dict[tuple[str, ...], ScheduleIssue]:
        issues: dict[tuple[str, ...], ScheduleIssue] = {}
        conflicts = self._conflict_detector.find_conflicts(
            [location.exam for location in flatten_exam_system(schedule)]
        )

        for conflict in conflicts:
            course_ids = tuple(
                sorted(
                    (
                        conflict.first_exam.course.course_number,
                        conflict.second_exam.course.course_number,
                    )
                )
            )
            issue_key = (
                "V2.0-critical-conflict-rule",
                conflict.first_exam.exam_date.isoformat(),
                conflict.program_number,
                str(conflict.year),
                *course_ids,
            )
            issues[issue_key] = ScheduleIssue(
                issue_key=issue_key,
                requirement_id="V2.0-critical-conflict-rule",
                explanation=(
                    f"Courses {course_ids[0]} and {course_ids[1]} conflict "
                    f"on {conflict.first_exam.exam_date} for program "
                    f"{conflict.program_number} year {conflict.year}."
                ),
                course_ids=course_ids,
                exam_date=conflict.first_exam.exam_date,
            )

        return issues

    @staticmethod
    def _max_exams_per_day_issues(
        schedule: ExamSystem,
        settings: SchedulingConstraintSettings | None,
    ) -> dict[tuple[str, ...], ScheduleIssue]:
        max_exams = _active_max_exams_per_day(settings)
        if max_exams is None:
            return {}

        counts = Counter(
            location.exam_date
            for location in flatten_exam_system(schedule)
        )
        issues: dict[tuple[str, ...], ScheduleIssue] = {}

        for exam_date, count in counts.items():
            if count <= max_exams:
                continue

            issue_key = ("Req 2.5", exam_date.isoformat())
            issues[issue_key] = ScheduleIssue(
                issue_key=issue_key,
                requirement_id="Req 2.5",
                explanation=(
                    f"{count} exams are scheduled on {exam_date}; "
                    f"maximum allowed is {max_exams}."
                ),
                exam_date=exam_date,
            )

        return issues

    @staticmethod
    def _ordered_values(
        issue_map: dict[tuple[str, ...], ScheduleIssue],
        keys: set[tuple[str, ...]],
    ) -> list[ScheduleIssue]:
        return [
            issue_map[key]
            for key in sorted(keys)
        ]


def _active_max_exams_per_day(
    settings: SchedulingConstraintSettings | None,
) -> int | None:
    if settings is None:
        return None

    setting = settings.constraints.get(ThresholdConstraintType.max_exams_per_day)
    if setting is None or not setting.enabled:
        return None

    return setting.k
