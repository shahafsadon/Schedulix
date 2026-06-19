from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ProgramEnrollment
from scheduling.constraints import (
    ConstraintEvaluationContext,
    ConstraintEvaluationResult,
    ConstraintRegistry,
    MandatoryGapDaysConstraint,
    MaxExamsPerDayConstraint,
    SameDateProgramYearConflictConstraint,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamScheduleGenerator, ExamSystem


def course(number: str, status: str = "Obligatory") -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", status)],
        evaluation_type="Exam",
    )


@dataclass
class FakeConstraint:
    result: ConstraintEvaluationResult
    enabled: bool = True
    incremental: bool = True
    final: bool = True
    name: str = "fake"
    requirement_id: str = "fake-req"
    calls: int = 0

    def evaluate(
        self,
        context: ConstraintEvaluationContext,
    ) -> ConstraintEvaluationResult:
        self.calls += 1
        return self.result


def test_registry_does_not_evaluate_disabled_constraints() -> None:
    disabled = FakeConstraint(
        enabled=False,
        result=ConstraintEvaluationResult.reject("disabled", "should not run"),
    )
    enabled = FakeConstraint(
        result=ConstraintEvaluationResult.accept(),
    )

    result = ConstraintRegistry([disabled, enabled]).evaluate_incremental(
        ConstraintEvaluationContext()
    )

    assert result.accepted
    assert disabled.calls == 0
    assert enabled.calls == 1


def test_registry_returns_first_violated_requirement_and_explanation() -> None:
    first = FakeConstraint(
        result=ConstraintEvaluationResult.reject(
            "Req X",
            "Candidate is invalid.",
        ),
    )
    second = FakeConstraint(
        result=ConstraintEvaluationResult.accept(),
    )

    result = ConstraintRegistry([first, second]).evaluate_incremental(
        ConstraintEvaluationContext()
    )

    assert not result.accepted
    assert result.violated_requirement == "Req X"
    assert result.explanation == "Candidate is invalid."
    assert first.calls == 1
    assert second.calls == 0


def test_same_date_program_year_constraint_can_be_tested_independently() -> None:
    existing = ScheduledExam(
        course=course("83102", "Obligatory"),
        exam_date=date(2026, 1, 1),
    )

    result = SameDateProgramYearConflictConstraint().evaluate(
        ConstraintEvaluationContext(
            candidate_exam=course("83103", "Elective"),
            candidate_date=date(2026, 1, 1),
            partial_schedule=[existing],
        )
    )

    assert not result.accepted
    assert result.violated_requirement == "V2.0-critical-conflict-rule"
    assert "program 83101 year 1" in result.explanation


def test_disabled_threshold_constraints_are_not_registered_from_settings() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = ThresholdConstraintSetting(
        enabled=True,
        k=1,
    )

    registry = ConstraintRegistry.default(settings)

    names = [constraint.name for constraint in registry.constraints]
    assert "max_exams_per_day" in names
    assert "mandatory_gap_days" not in names
    assert "any_course_gap_days" not in names


def test_generator_uses_constraint_registry_abstraction_to_reject_candidates() -> None:
    rejecting_registry = ConstraintRegistry(
        [
            FakeConstraint(
                result=ConstraintEvaluationResult.reject(
                    "Test requirement",
                    "Rejected by injected abstraction.",
                )
            )
        ]
    )
    generator = ExamScheduleGenerator(constraint_registry=rejecting_registry)
    period = __import__("models").ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        excluded_dates=[],
    )

    schedules = generator.generate_for_period([course("83102")], period)

    assert schedules == []


def test_final_constraint_rejects_complete_system_after_generation() -> None:
    registry = ConstraintRegistry(
        [
            MaxExamsPerDayConstraint(k=1),
        ]
    )
    exam_system = ExamSystem(
        [
            ExamSchedule(
                "FALL",
                "Aleph",
                [
                    ScheduledExam(course("83102"), date(2026, 1, 1)),
                    ScheduledExam(course("83103", "Elective"), date(2026, 1, 1)),
                ],
            )
        ]
    )

    result = registry.evaluate_final(ConstraintEvaluationContext(exam_system=exam_system))

    assert not result.accepted
    assert result.violated_requirement == "Req 2.5"


def test_mandatory_gap_days_constraint_rejects_close_mandatory_exams() -> None:
    result = MandatoryGapDaysConstraint(k=3).evaluate(
        ConstraintEvaluationContext(
            candidate_exam=course("83103"),
            candidate_date=date(2026, 1, 2),
            partial_schedule=[
                ScheduledExam(course("83102"), date(2026, 1, 1)),
            ],
        )
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.1"