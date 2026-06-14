from __future__ import annotations

from datetime import date

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.constraints import (
    ConstraintEvaluationContext,
    ConstraintRegistry,
    MandatorySpanDaysConstraint,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamScheduleGenerator, ExamSystem


def course(
    number: str,
    programs: list[ProgramEnrollment],
) -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=programs,
        evaluation_type="Exam",
    )


def enrollment(
    program_number: str = "83101",
    year: int = 1,
    semester: str = "FALL",
    status: str = "Obligatory",
) -> ProgramEnrollment:
    return ProgramEnrollment(
        program_number=program_number,
        year=year,
        semester=semester,
        status=status,
    )


def scheduled_exam(
    number: str,
    exam_date: date,
    programs: list[ProgramEnrollment] | None = None,
) -> ScheduledExam:
    return ScheduledExam(
        course=course(
            number,
            programs or [enrollment()],
        ),
        exam_date=exam_date,
    )


def exam_system_for_period(
    scheduled_exams: list[ScheduledExam],
    semester: str = "FALL",
    moed: str = "Aleph",
) -> ExamSystem:
    return ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester=semester,
                moed=moed,
                scheduled_exams=scheduled_exams,
            )
        ]
    )


def evaluate_system(
    exam_system: ExamSystem,
    k: int,
):
    return MandatorySpanDaysConstraint(k=k).evaluate(
        ConstraintEvaluationContext(
            exam_system=exam_system,
        )
    )


def test_rejects_group_when_mandatory_span_is_smaller_than_k() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam("83102", date(2026, 1, 10)),
                scheduled_exam("83103", date(2026, 1, 12)),
            ]
        ),
        k=3,
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.4"
    assert "program 83101 year 1" in result.explanation
    assert "semester FALL moed Aleph" in result.explanation
    assert "span only 2 days" in result.explanation
    assert "required minimum is 3" in result.explanation


def test_accepts_group_when_mandatory_span_equals_k() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam("83102", date(2026, 1, 10)),
                scheduled_exam("83103", date(2026, 1, 13)),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_accepts_group_when_mandatory_span_is_larger_than_k() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam("83102", date(2026, 1, 10)),
                scheduled_exam("83103", date(2026, 1, 14)),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_group_with_zero_mandatory_exams_is_accepted() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam(
                    "83102",
                    date(2026, 1, 10),
                    [enrollment(status="Elective")],
                ),
                scheduled_exam(
                    "83103",
                    date(2026, 1, 12),
                    [enrollment(status="Elective")],
                ),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_group_with_one_mandatory_exam_is_accepted() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam("83102", date(2026, 1, 10)),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_elective_exams_do_not_affect_mandatory_span() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam("83102", date(2026, 1, 10)),
                scheduled_exam(
                    "83103",
                    date(2026, 1, 20),
                    [enrollment(status="Elective")],
                ),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_different_programs_are_evaluated_separately() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam(
                    "83102",
                    date(2026, 1, 10),
                    [enrollment(program_number="83101")],
                ),
                scheduled_exam(
                    "83103",
                    date(2026, 1, 11),
                    [enrollment(program_number="83102")],
                ),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_different_study_years_are_evaluated_separately() -> None:
    result = evaluate_system(
        exam_system=exam_system_for_period(
            [
                scheduled_exam(
                    "83102",
                    date(2026, 1, 10),
                    [enrollment(year=1)],
                ),
                scheduled_exam(
                    "83103",
                    date(2026, 1, 11),
                    [enrollment(year=2)],
                ),
            ]
        ),
        k=3,
    )

    assert result.accepted


def test_different_moeds_are_evaluated_separately() -> None:
    exam_system = ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=[
                    scheduled_exam("83102", date(2026, 1, 10)),
                ],
            ),
            ExamSchedule(
                semester="FALL",
                moed="Bet",
                scheduled_exams=[
                    scheduled_exam("83103", date(2026, 1, 11)),
                ],
            ),
        ]
    )

    result = evaluate_system(
        exam_system=exam_system,
        k=3,
    )

    assert result.accepted


def test_same_program_year_and_moed_across_multiple_period_schedules_is_rejected() -> None:
    exam_system = ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=[
                    scheduled_exam("83102", date(2026, 1, 10)),
                ],
            ),
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=[
                    scheduled_exam("83103", date(2026, 1, 11)),
                ],
            ),
        ]
    )

    result = evaluate_system(
        exam_system=exam_system,
        k=3,
    )

    assert not result.accepted
    assert "program 83101 year 1" in result.explanation
    assert "semester FALL moed Aleph" in result.explanation


def test_rule_works_across_all_selected_programs_in_multi_program_courses() -> None:
    exam_system = exam_system_for_period(
        [
            scheduled_exam(
                "83102",
                date(2026, 1, 10),
                [
                    enrollment(program_number="83101", year=1),
                    enrollment(program_number="83102", year=2),
                ],
            ),
            scheduled_exam(
                "83103",
                date(2026, 1, 11),
                [
                    enrollment(program_number="99999", year=1),
                    enrollment(program_number="83102", year=2),
                ],
            ),
        ]
    )

    result = evaluate_system(
        exam_system=exam_system,
        k=3,
    )

    assert not result.accepted
    assert "program 83102 year 2" in result.explanation


def test_constraint_is_final_only_not_incremental() -> None:
    constraint = MandatorySpanDaysConstraint(k=3)

    assert not constraint.incremental
    assert constraint.final
    assert constraint.requires_final_system_evaluation


def test_registry_requires_final_system_evaluation_when_span_constraint_is_enabled() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_span_days] = ThresholdConstraintSetting(
        enabled=True,
        k=3,
    )

    registry = ConstraintRegistry.default(settings)

    assert registry.requires_final_system_evaluation()


def test_enabled_span_constraint_filters_invalid_complete_systems_during_generation() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_span_days] = ThresholdConstraintSetting(
        enabled=True,
        k=3,
    )

    generator = ExamScheduleGenerator(
        constraint_registry=ConstraintRegistry.default(settings)
    )
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 11),
        excluded_dates=[],
    )

    systems = list(
        generator.iter_exam_systems(
            courses=[
                course("83102", [enrollment()]),
                course("83103", [enrollment()]),
            ],
            exam_periods=[exam_period],
        )
    )

    assert systems == []


def test_disabled_span_constraint_keeps_other_version_2_behavior() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_span_days] = ThresholdConstraintSetting(
        enabled=False,
        k=3,
    )

    generator = ExamScheduleGenerator(
        constraint_registry=ConstraintRegistry.default(settings)
    )
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 11),
        excluded_dates=[],
    )

    systems = list(
        generator.iter_exam_systems(
            courses=[
                course("83102", [enrollment()]),
                course("83103", [enrollment()]),
            ],
            exam_periods=[exam_period],
        )
    )

    assert len(systems) == 2