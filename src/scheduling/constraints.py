from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from constraint_settings import SchedulingConstraintSettings, ThresholdConstraintType
from models import Course
from scheduling.examConflictDetector import ExamConflictDetector, ScheduledExam


ResourceKey = tuple[str, int]
ELECTIVE = "elective"


@dataclass(frozen=True)
class ConstraintEvaluationResult:
    """Result returned by one schedule constraint evaluation."""

    accepted: bool
    violated_requirement: str | None = None
    explanation: str | None = None

    @classmethod
    def accept(cls) -> ConstraintEvaluationResult:
        return cls(accepted=True)

    @classmethod
    def reject(
        cls,
        violated_requirement: str,
        explanation: str,
    ) -> ConstraintEvaluationResult:
        return cls(
            accepted=False,
            violated_requirement=violated_requirement,
            explanation=explanation,
        )


@dataclass(frozen=True)
class ConstraintEvaluationContext:
    """Input data available to schedule constraints."""

    candidate_exam: Course | None = None
    candidate_date: date | None = None
    partial_schedule: list[ScheduledExam] = field(default_factory=list)
    exam_system: Any | None = None
    semester: str | None = None
    moed: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ScheduleConstraint(Protocol):
    """Common contract for every scheduling constraint evaluator."""

    name: str
    requirement_id: str
    enabled: bool
    incremental: bool
    final: bool
    requires_final_system_evaluation: bool

    def evaluate(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        """Evaluate this constraint against the supplied context."""


@dataclass(frozen=True)
class NoDuplicateCourseOnSameDateConstraint:
    """Prevent the same course from being placed twice on one date."""

    enabled: bool = True
    name: str = "no_duplicate_course_on_same_date"
    requirement_id: str = "V2.0-overlapping-period-course-date"
    incremental: bool = True
    final: bool = True
    requires_final_system_evaluation: bool = False

    def evaluate(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        if context.candidate_exam is not None:
            return self._evaluate_candidate(context)

        if context.exam_system is not None:
            return self._evaluate_system(context)

        return ConstraintEvaluationResult.accept()

    def _evaluate_candidate(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        if context.candidate_date is None:
            return ConstraintEvaluationResult.accept()

        course_number = context.candidate_exam.course_number
        course_numbers_by_date = context.metadata.get("course_numbers_by_date")

        if course_numbers_by_date is not None:
            if course_number in course_numbers_by_date.get(context.candidate_date, set()):
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Course {course_number} already has an exam on {context.candidate_date}.",
                )

            return ConstraintEvaluationResult.accept()

        for scheduled_exam in context.partial_schedule:
            if (
                scheduled_exam.exam_date == context.candidate_date
                and scheduled_exam.course.course_number == course_number
            ):
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Course {course_number} already has an exam on {context.candidate_date}.",
                )

        return ConstraintEvaluationResult.accept()

    def _evaluate_system(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        seen: set[tuple[str, date]] = set()

        for scheduled_exam in _flatten_exam_system(context.exam_system):
            key = (
                scheduled_exam.course.course_number,
                scheduled_exam.exam_date,
            )

            if key in seen:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Course {key[0]} appears more than once on {key[1]}.",
                )

            seen.add(key)

        return ConstraintEvaluationResult.accept()


@dataclass(frozen=True)
class SameDateProgramYearConflictConstraint:
    """Version 2.0 critical conflict rule for same-date program/year exams."""

    enabled: bool = True
    name: str = "same_date_program_year_conflict"
    requirement_id: str = "V2.0-critical-conflict-rule"
    incremental: bool = True
    final: bool = True
    requires_final_system_evaluation: bool = False

    def evaluate(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        if context.candidate_exam is not None:
            return self._evaluate_candidate(context)

        if context.exam_system is not None:
            scheduled_exams = _flatten_exam_system(context.exam_system)
            if ExamConflictDetector().has_conflicts(scheduled_exams):
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    "The completed system contains two same-date exams for the same program/year where at least one is mandatory.",
                )

        return ConstraintEvaluationResult.accept()

    def _evaluate_candidate(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        if context.candidate_date is None:
            return ConstraintEvaluationResult.accept()

        obligatory_keys, elective_keys = _resource_keys(context.candidate_exam)
        day_usage = self._day_usage(context)

        for key in obligatory_keys:
            usage = day_usage.get(key)
            if usage is not None and usage[0] > 0:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    _same_date_rejection_message(context.candidate_exam, context.candidate_date, key),
                )

        for key in elective_keys:
            usage = day_usage.get(key)
            if usage is not None and usage[1] > 0:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    _same_date_rejection_message(context.candidate_exam, context.candidate_date, key),
                )

        return ConstraintEvaluationResult.accept()

    @staticmethod
    def _day_usage(
        context: ConstraintEvaluationContext,
    ) -> dict[ResourceKey, list[int]]:
        occupancy = context.metadata.get("occupancy")
        if occupancy is not None:
            return occupancy.get(context.candidate_date, {})

        day_usage: dict[ResourceKey, list[int]] = {}
        for scheduled_exam in context.partial_schedule:
            if scheduled_exam.exam_date != context.candidate_date:
                continue

            obligatory_keys, elective_keys = _resource_keys(scheduled_exam.course)
            for key in obligatory_keys:
                usage = day_usage.setdefault(key, [0, 0])
                usage[0] += 1
                usage[1] += 1
            for key in elective_keys:
                usage = day_usage.setdefault(key, [0, 0])
                usage[0] += 1

        return day_usage


@dataclass(frozen=True)
class MandatoryGapDaysConstraint:
    """Require mandatory exams in the same program/year to be at least k days apart."""

    k: int
    enabled: bool = True
    name: str = "mandatory_gap_days"
    requirement_id: str = "Req 2.1"
    incremental: bool = True
    final: bool = True

    def evaluate(self, context: ConstraintEvaluationContext) -> ConstraintEvaluationResult:
        if context.candidate_exam is not None and context.candidate_date is not None:
            indexed_result = _evaluate_candidate_gap_with_index(
                context=context,
                candidate_keys_metadata_name="candidate_obligatory_keys",
                date_index_metadata_name="mandatory_dates_by_key",
                fallback_keys=_mandatory_keys,
                requirement_id=self.requirement_id,
                threshold=self.k,
                explanation_prefix="Mandatory exams",
            )
            if indexed_result is not None:
                return indexed_result

        entries = _entries_with_candidate(context)
        by_group = _dates_by_program_year(entries, mandatory_only=True)

        for key, dates in by_group.items():
            violation = _first_gap_below_threshold(dates, self.k)
            if violation is not None:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Mandatory exams for program {key[0]} year {key[1]} are only {violation} days apart; required minimum is {self.k}.",
                )

        return ConstraintEvaluationResult.accept()


@dataclass(frozen=True)
class AnyCourseGapDaysConstraint:
    """Require any exams sharing a program/year to be at least k days apart."""

    k: int
    enabled: bool = True
    name: str = "any_course_gap_days"
    requirement_id: str = "Req 2.2"
    incremental: bool = True
    final: bool = True

    def evaluate(self, context: ConstraintEvaluationContext) -> ConstraintEvaluationResult:
        if context.candidate_exam is not None and context.candidate_date is not None:
            indexed_result = _evaluate_candidate_gap_with_index(
                context=context,
                candidate_keys_metadata_name="candidate_all_keys",
                date_index_metadata_name="all_dates_by_key",
                fallback_keys=_all_keys,
                requirement_id=self.requirement_id,
                threshold=self.k,
                explanation_prefix="Exams",
            )
            if indexed_result is not None:
                return indexed_result

        entries = _entries_with_candidate(context)
        by_group = _dates_by_program_year(entries, mandatory_only=False)

        for key, dates in by_group.items():
            violation = _first_gap_below_threshold(dates, self.k)
            if violation is not None:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Exams for program {key[0]} year {key[1]} are only {violation} days apart; required minimum is {self.k}.",
                )

        return ConstraintEvaluationResult.accept()


@dataclass(frozen=True)
class ElectiveConflictsPerProgramConstraint:
    """Limit same-date elective/elective collisions per program."""

    k: int
    enabled: bool = True
    name: str = "elective_conflicts_per_program"
    requirement_id: str = "Req 2.3"
    incremental: bool = True
    final: bool = True

    def evaluate(self, context: ConstraintEvaluationContext) -> ConstraintEvaluationResult:
        if context.candidate_exam is not None and context.candidate_date is not None:
            indexed_result = self._evaluate_candidate_with_index(context)
            if indexed_result is not None:
                return indexed_result

        entries = _entries_with_candidate(context)
        counts: dict[str, int] = defaultdict(int)

        by_date: dict[date, list[ScheduledExam]] = defaultdict(list)
        for scheduled_exam in entries:
            by_date[scheduled_exam.exam_date].append(scheduled_exam)

        for same_day_exams in by_date.values():
            for index, first_exam in enumerate(same_day_exams):
                for second_exam in same_day_exams[index + 1:]:
                    shared_programs = _elective_programs(first_exam.course).intersection(
                        _elective_programs(second_exam.course)
                    )
                    for program_number in shared_programs:
                        counts[program_number] += 1

        for program_number, count in counts.items():
            if count > self.k:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Program {program_number} has {count} elective same-date collisions; maximum allowed is {self.k}.",
                )

        return ConstraintEvaluationResult.accept()


    def _evaluate_candidate_with_index(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult | None:
        elective_counts_by_date_program = context.metadata.get(
            "elective_counts_by_date_program"
        )
        elective_collisions_by_program = context.metadata.get(
            "elective_collisions_by_program"
        )

        if (
            elective_counts_by_date_program is None
            or elective_collisions_by_program is None
        ):
            return None

        candidate_programs = context.metadata.get("candidate_elective_programs")
        if candidate_programs is None:
            candidate_programs = _elective_programs(context.candidate_exam)

        same_date_counts = elective_counts_by_date_program.get(
            context.candidate_date,
            {},
        )

        for program_number in candidate_programs:
            resulting_count = (
                elective_collisions_by_program.get(program_number, 0)
                + same_date_counts.get(program_number, 0)
            )
            if resulting_count > self.k:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Program {program_number} has {resulting_count} elective same-date collisions; maximum allowed is {self.k}.",
                )

        return ConstraintEvaluationResult.accept()


@dataclass(frozen=True)
class MandatorySpanDaysConstraint:
    """Require the mandatory exam-period span to be at least k days."""

    k: int
    enabled: bool = True
    name: str = "mandatory_span_days"
    requirement_id: str = "Req 2.4"
    incremental: bool = False
    final: bool = True
    requires_final_system_evaluation: bool = True

    def evaluate(self, context: ConstraintEvaluationContext) -> ConstraintEvaluationResult:
        entries = _period_entries_with_candidate(context)
        by_group: dict[tuple[str, int, str | None, str | None], list[date]] = defaultdict(list)

        for scheduled_exam, semester, moed in entries:
            for program_number, year in _mandatory_keys(scheduled_exam.course):
                by_group[(program_number, year, semester, moed)].append(
                    scheduled_exam.exam_date
                )

        for key, dates in by_group.items():
            if len(dates) < 2:
                continue

            span = (max(dates) - min(dates)).days
            if span < self.k:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    (
                        f"Mandatory exams for program {key[0]} year {key[1]} "
                        f"semester {key[2]} moed {key[3]} span only {span} days; "
                        f"required minimum is {self.k}."
                    ),
                )

        return ConstraintEvaluationResult.accept()


@dataclass(frozen=True)
class MaxExamsPerDayConstraint:
    """Limit the total number of exams on one calendar date."""

    k: int
    enabled: bool = True
    name: str = "max_exams_per_day"
    requirement_id: str = "Req 2.5"
    incremental: bool = True
    final: bool = True

    def evaluate(self, context: ConstraintEvaluationContext) -> ConstraintEvaluationResult:
        if context.candidate_date is not None:
            exam_counts_by_date = context.metadata.get("exam_counts_by_date")
            if exam_counts_by_date is not None:
                count = exam_counts_by_date.get(context.candidate_date, 0) + 1
                if count > self.k:
                    return ConstraintEvaluationResult.reject(
                        self.requirement_id,
                        f"Date {context.candidate_date} has {count} exams; maximum allowed is {self.k}.",
                    )

                return ConstraintEvaluationResult.accept()

        counts: dict[date, int] = defaultdict(int)

        for scheduled_exam in _entries_with_candidate(context):
            counts[scheduled_exam.exam_date] += 1

        for exam_date, count in counts.items():
            if count > self.k:
                return ConstraintEvaluationResult.reject(
                    self.requirement_id,
                    f"Date {exam_date} has {count} exams; maximum allowed is {self.k}.",
                )

        return ConstraintEvaluationResult.accept()


class ConstraintRegistry:
    """Stores enabled constraints and evaluates them by phase."""

    def __init__(
        self,
        constraints: Iterable[ScheduleConstraint] | None = None,
    ) -> None:
        self._constraints = [
            constraint
            for constraint in (constraints or [])
            if constraint.enabled
        ]

    @classmethod
    def default(
        cls,
        settings: SchedulingConstraintSettings | None = None,
    ) -> ConstraintRegistry:
        constraints: list[ScheduleConstraint] = [
            NoDuplicateCourseOnSameDateConstraint(),
            SameDateProgramYearConflictConstraint(),
        ]

        if settings is not None:
            constraints.extend(_threshold_constraints_from_settings(settings))

        return cls(constraints)

    @property
    def constraints(self) -> tuple[ScheduleConstraint, ...]:
        return tuple(self._constraints)

    def requires_final_system_evaluation(self) -> bool:
        return any(
            getattr(
                constraint,
                "requires_final_system_evaluation",
                constraint.final,
            )
            for constraint in self._constraints
            if constraint.final
        )

    def evaluate_incremental(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        for constraint in self._constraints:
            if not constraint.incremental:
                continue

            result = constraint.evaluate(context)
            if not result.accepted:
                return result

        return ConstraintEvaluationResult.accept()

    def evaluate_final(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        for constraint in self._constraints:
            if not constraint.final:
                continue

            result = constraint.evaluate(context)
            if not result.accepted:
                return result

        return ConstraintEvaluationResult.accept()


def _evaluate_candidate_gap_with_index(
    context: ConstraintEvaluationContext,
    candidate_keys_metadata_name: str,
    date_index_metadata_name: str,
    fallback_keys,
    requirement_id: str,
    threshold: int,
    explanation_prefix: str,
) -> ConstraintEvaluationResult | None:
    date_index = context.metadata.get(date_index_metadata_name)
    if date_index is None:
        return None

    candidate_keys = context.metadata.get(candidate_keys_metadata_name)
    if candidate_keys is None:
        candidate_keys = fallback_keys(context.candidate_exam)

    for key in candidate_keys:
        for existing_date in date_index.get(key, []):
            gap = abs((context.candidate_date - existing_date).days)
            if gap < threshold:
                return ConstraintEvaluationResult.reject(
                    requirement_id,
                    f"{explanation_prefix} for program {key[0]} year {key[1]} are only {gap} days apart; required minimum is {threshold}.",
                )

    return ConstraintEvaluationResult.accept()


def _threshold_constraints_from_settings(
    settings: SchedulingConstraintSettings,
) -> list[ScheduleConstraint]:
    factories = {
        ThresholdConstraintType.mandatory_gap_days: MandatoryGapDaysConstraint,
        ThresholdConstraintType.any_course_gap_days: AnyCourseGapDaysConstraint,
        ThresholdConstraintType.elective_conflicts_per_program: ElectiveConflictsPerProgramConstraint,
        ThresholdConstraintType.mandatory_span_days: MandatorySpanDaysConstraint,
        ThresholdConstraintType.max_exams_per_day: MaxExamsPerDayConstraint,
    }

    constraints: list[ScheduleConstraint] = []
    for constraint_type, factory in factories.items():
        setting = settings.constraints.get(constraint_type)
        if setting is None or not setting.enabled:
            continue

        constraints.append(factory(k=setting.k))

    return constraints


def _entries_with_candidate(
    context: ConstraintEvaluationContext,
) -> list[ScheduledExam]:
    entries = list(context.partial_schedule)

    if context.exam_system is not None:
        entries.extend(_flatten_exam_system(context.exam_system))

    if context.candidate_exam is not None and context.candidate_date is not None:
        entries.append(
            ScheduledExam(
                course=context.candidate_exam,
                exam_date=context.candidate_date,
            )
        )

    return entries


def _period_entries_with_candidate(
    context: ConstraintEvaluationContext,
) -> list[tuple[ScheduledExam, str | None, str | None]]:
    entries: list[tuple[ScheduledExam, str | None, str | None]] = [
        (scheduled_exam, context.semester, context.moed)
        for scheduled_exam in context.partial_schedule
    ]

    if context.exam_system is not None:
        for period_schedule in context.exam_system.period_schedules:
            for scheduled_exam in period_schedule.scheduled_exams:
                entries.append((scheduled_exam, period_schedule.semester, period_schedule.moed))

    if context.candidate_exam is not None and context.candidate_date is not None:
        entries.append(
            (
                ScheduledExam(context.candidate_exam, context.candidate_date),
                context.semester,
                context.moed,
            )
        )

    return entries


def _flatten_exam_system(exam_system: Any) -> list[ScheduledExam]:
    scheduled_exams: list[ScheduledExam] = []

    for period_schedule in exam_system.period_schedules:
        scheduled_exams.extend(period_schedule.scheduled_exams)

    return scheduled_exams


def _dates_by_program_year(
    scheduled_exams: list[ScheduledExam],
    mandatory_only: bool,
) -> dict[ResourceKey, list[date]]:
    dates_by_group: dict[ResourceKey, list[date]] = defaultdict(list)

    for scheduled_exam in scheduled_exams:
        if mandatory_only:
            keys = _mandatory_keys(scheduled_exam.course)
        else:
            keys = _all_keys(scheduled_exam.course)

        for key in keys:
            dates_by_group[key].append(scheduled_exam.exam_date)

    return dates_by_group


def _first_gap_below_threshold(
    dates: list[date],
    threshold: int,
) -> int | None:
    sorted_dates = sorted(dates)

    for first_date, second_date in zip(sorted_dates, sorted_dates[1:]):
        gap = (second_date - first_date).days
        if gap < threshold:
            return gap

    return None


def _resource_keys(course: Course) -> tuple[set[ResourceKey], set[ResourceKey]]:
    obligatory = _mandatory_keys(course)
    elective = {
        (program.program_number, program.year)
        for program in course.programs
        if _is_elective(program.status)
    }
    elective.difference_update(obligatory)
    return obligatory, elective


def _mandatory_keys(course: Course) -> set[ResourceKey]:
    return {
        (program.program_number, program.year)
        for program in course.programs
        if not _is_elective(program.status)
    }


def _all_keys(course: Course) -> set[ResourceKey]:
    return {
        (program.program_number, program.year)
        for program in course.programs
    }


def _elective_programs(course: Course) -> set[str]:
    mandatory_programs = {
        program.program_number
        for program in course.programs
        if not _is_elective(program.status)
    }
    elective_programs = {
        program.program_number
        for program in course.programs
        if _is_elective(program.status)
    }
    return elective_programs.difference(mandatory_programs)


def _is_elective(status: str) -> bool:
    return status.strip().lower() == ELECTIVE


def _same_date_rejection_message(
    course: Course,
    exam_date: date,
    key: ResourceKey,
) -> str:
    return (
        f"Course {course.course_number} cannot be placed on {exam_date}: "
        f"program {key[0]} year {key[1]} already has a conflicting exam."
    )
