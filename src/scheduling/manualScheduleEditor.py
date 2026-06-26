"""Apply one safe manual exam move.

The editor never changes the original schedule directly. It creates a copied
schedule, moves one course exam, validates the result, and returns a clear
success or failure object for the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from constraint_settings import SchedulingConstraintSettings
from scheduling.constraints import ConstraintEvaluationContext, ConstraintRegistry
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.impactAnalysisService import ImpactAnalysisResult, ImpactAnalysisService
from scheduling.scheduleIntrospection import clone_exam_system_with_move


@dataclass(frozen=True)
class ManualMoveResult:
    """Result of trying to move one exam by hand."""

    success: bool
    message: str
    schedule: ExamSystem | None = None
    course_id: str | None = None
    old_date: date | None = None
    new_date: date | None = None
    errors: list[str] = field(default_factory=list)
    impact: ImpactAnalysisResult | None = None


class ManualScheduleEditor:
    """Moves one exam date on a copied schedule and validates it."""

    def __init__(
        self,
        impact_service: ImpactAnalysisService | None = None,
    ) -> None:
        self._impact_service = impact_service or ImpactAnalysisService()

    def move_exam(
        self,
        schedule: ExamSystem,
        course_id: str,
        target_date: date | str,
        *,
        source_semester: str | None = None,
        source_moed: str | None = None,
        source_date: date | None = None,
        constraint_settings: SchedulingConstraintSettings | None = None,
        available_dates: set[date] | list[date] | tuple[date, ...] | None = None,
    ) -> ManualMoveResult:
        """Move one selected course-period exam if the result stays valid."""
        clean_course_id = course_id.strip()
        if not clean_course_id:
            return self._failure("Course id cannot be empty.")

        parsed_date = self._parse_target_date(target_date)
        if parsed_date is None:
            return self._failure("Target date must be DD-MM-YYYY or YYYY-MM-DD.")

        if available_dates is not None and parsed_date not in set(available_dates):
            return self._failure(f"Date {parsed_date} is not available.")

        modified, old_date, error = clone_exam_system_with_move(
            schedule,
            clean_course_id,
            parsed_date,
            source_semester=source_semester,
            source_moed=source_moed,
            source_date=source_date,
        )
        if modified is None:
            return self._failure(error or "Move could not be applied.")

        validation_error = self._validation_error(modified, constraint_settings)
        if validation_error is not None:
            return self._failure(validation_error)

        return ManualMoveResult(
            success=True,
            message=f"Course {clean_course_id} moved to {parsed_date}.",
            schedule=modified,
            course_id=clean_course_id,
            old_date=old_date,
            new_date=parsed_date,
            impact=self._impact_service.analyze(
                schedule,
                modified,
                constraint_settings,
            ),
        )

    @staticmethod
    def _parse_target_date(target_date: date | str) -> date | None:
        if isinstance(target_date, date):
            return target_date

        text = target_date.strip()
        for date_format in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue

        return None

    @staticmethod
    def _validation_error(
        schedule: ExamSystem,
        settings: SchedulingConstraintSettings | None,
    ) -> str | None:
        registry = ConstraintRegistry.default(settings)
        result = registry.evaluate_final(
            ConstraintEvaluationContext(exam_system=schedule)
        )

        if result.accepted:
            return None

        requirement = result.violated_requirement or "unknown requirement"
        explanation = result.explanation or "The modified schedule is invalid."
        return f"{requirement}: {explanation}"

    @staticmethod
    def _failure(message: str) -> ManualMoveResult:
        return ManualMoveResult(
            success=False,
            message=message,
            errors=[message],
        )
