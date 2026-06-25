"""Penalty scoring for fallback schedules and snapshot comparison.

The normal scheduler treats every enabled threshold constraint as strict.  This
module is used only when the application needs to explain a fallback schedule:
hard red-line constraints remain enforced by the generator, while soft
threshold violations are converted into a deterministic penalty score.
"""

from __future__ import annotations

from dataclasses import dataclass

from constraint_settings import SchedulingConstraintSettings, ThresholdConstraintType
from scheduling.constraints import (
    AnyCourseGapDaysConstraint,
    ConstraintEvaluationContext,
    ElectiveConflictsPerProgramConstraint,
    MandatoryGapDaysConstraint,
    MandatorySpanDaysConstraint,
    MaxExamsPerDayConstraint,
    NoDuplicateCourseOnSameDateConstraint,
    SameDateProgramYearConflictConstraint,
    ScheduleConstraint,
)
from scheduling.examScheduleGenerator import ExamSystem


_PENALTY_BY_CONSTRAINT: dict[ThresholdConstraintType, float] = {
    ThresholdConstraintType.any_course_gap_days: 10.0,
    ThresholdConstraintType.elective_conflicts_per_program: 10.0,
    ThresholdConstraintType.mandatory_gap_days: 50.0,
    ThresholdConstraintType.mandatory_span_days: 50.0,
    ThresholdConstraintType.max_exams_per_day: 50.0,
}


@dataclass(frozen=True)
class PenaltyViolation:
    """One soft-constraint violation converted into a fallback penalty."""

    requirement_id: str
    explanation: str
    penalty: float

    def display_text(self) -> str:
        """Return a compact user-facing violation line."""
        return f"{self.requirement_id}: {self.explanation} (penalty {self.penalty:g})"


@dataclass(frozen=True)
class PenaltyScoreResult:
    """Penalty score and violation details for one complete schedule."""

    total_score: float
    violations: tuple[PenaltyViolation, ...]

    @property
    def details(self) -> tuple[str, ...]:
        """Return display-ready violation details."""
        return tuple(violation.display_text() for violation in self.violations)


class SchedulePenaltyScorer:
    """Scores enabled soft-threshold violations on complete schedules."""

    def score(
        self,
        exam_system: ExamSystem,
        settings: SchedulingConstraintSettings | None,
    ) -> PenaltyScoreResult:
        """Return the total soft-constraint penalty for ``exam_system``."""
        violations: list[PenaltyViolation] = []
        for constraint_type, constraint in self._soft_constraints(settings):
            result = constraint.evaluate(
                ConstraintEvaluationContext(exam_system=exam_system)
            )
            if result.accepted:
                continue

            penalty = _PENALTY_BY_CONSTRAINT[constraint_type]
            violations.append(
                PenaltyViolation(
                    requirement_id=result.violated_requirement
                    or constraint.requirement_id,
                    explanation=result.explanation
                    or "Soft constraint was violated.",
                    penalty=penalty,
                )
            )

        return PenaltyScoreResult(
            total_score=sum(violation.penalty for violation in violations),
            violations=tuple(violations),
        )

    @staticmethod
    def hard_constraints() -> tuple[ScheduleConstraint, ...]:
        """Return non-negotiable red-line constraints for fallback generation."""
        return (
            NoDuplicateCourseOnSameDateConstraint(),
            SameDateProgramYearConflictConstraint(),
        )

    @staticmethod
    def _soft_constraints(
        settings: SchedulingConstraintSettings | None,
    ) -> list[tuple[ThresholdConstraintType, ScheduleConstraint]]:
        if settings is None:
            return []

        constraints: list[tuple[ThresholdConstraintType, ScheduleConstraint]] = []
        for constraint_type, setting in settings.constraints.items():
            if not setting.enabled:
                continue
            if constraint_type == ThresholdConstraintType.mandatory_gap_days:
                constraint = MandatoryGapDaysConstraint(setting.k)
            elif constraint_type == ThresholdConstraintType.any_course_gap_days:
                constraint = AnyCourseGapDaysConstraint(setting.k)
            elif constraint_type == ThresholdConstraintType.elective_conflicts_per_program:
                constraint = ElectiveConflictsPerProgramConstraint(setting.k)
            elif constraint_type == ThresholdConstraintType.mandatory_span_days:
                constraint = MandatorySpanDaysConstraint(setting.k)
            elif constraint_type == ThresholdConstraintType.max_exams_per_day:
                constraint = MaxExamsPerDayConstraint(setting.k)
            else:
                continue
            constraints.append((constraint_type, constraint))
        return constraints
