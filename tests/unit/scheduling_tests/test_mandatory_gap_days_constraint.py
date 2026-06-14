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
    MandatoryGapDaysConstraint,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamScheduleGenerator


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
    status: str = "Obligatory",
) -> ProgramEnrollment:
    return ProgramEnrollment(
        program_number=program_number,
        year=year,
        semester="FALL",
        status=status,
    )


def evaluate_candidate(
    existing_course: Course,
    existing_date: date,
    candidate_course: Course,
    candidate_date: date,
    k: int,
):
    return MandatoryGapDaysConstraint(k=k).evaluate(
        ConstraintEvaluationContext(
            candidate_exam=candidate_course,
            candidate_date=candidate_date,
            partial_schedule=[
                ScheduledExam(
                    course=existing_course,
                    exam_date=existing_date,
                )
            ],
        )
    )


def test_rejects_mandatory_exams_when_gap_is_smaller_than_k() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment()]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment()]),
        candidate_date=date(2026, 1, 12),
        k=3,
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.1"
    assert "only 2 days apart" in result.explanation
    assert "required minimum is 3" in result.explanation


def test_accepts_mandatory_exams_when_gap_equals_k() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment()]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment()]),
        candidate_date=date(2026, 1, 13),
        k=3,
    )

    assert result.accepted


def test_accepts_mandatory_exams_when_gap_is_larger_than_k() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment()]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment()]),
        candidate_date=date(2026, 1, 14),
        k=3,
    )

    assert result.accepted


def test_uses_absolute_calendar_day_difference_when_candidate_is_before_existing_exam() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment()]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment()]),
        candidate_date=date(2026, 1, 8),
        k=3,
    )

    assert not result.accepted
    assert "only 2 days apart" in result.explanation


def test_counts_weekends_and_holidays_as_normal_calendar_days() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment()]),
        existing_date=date(2026, 1, 2),
        candidate_course=course("83103", [enrollment()]),
        candidate_date=date(2026, 1, 5),
        k=3,
    )

    assert result.accepted


def test_different_programs_do_not_trigger_mandatory_gap_rule() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment(program_number="83101")]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment(program_number="83102")]),
        candidate_date=date(2026, 1, 11),
        k=3,
    )

    assert result.accepted


def test_different_study_years_do_not_trigger_mandatory_gap_rule() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment(year=1)]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment(year=2)]),
        candidate_date=date(2026, 1, 11),
        k=3,
    )

    assert result.accepted


def test_elective_enrollment_does_not_trigger_mandatory_gap_rule() -> None:
    result = evaluate_candidate(
        existing_course=course("83102", [enrollment(status="Elective")]),
        existing_date=date(2026, 1, 10),
        candidate_course=course("83103", [enrollment(status="Obligatory")]),
        candidate_date=date(2026, 1, 11),
        k=3,
    )

    assert result.accepted


def test_courses_with_multiple_programs_are_rejected_when_any_mandatory_program_year_overlaps() -> None:
    existing_course = course(
        "83102",
        [
            enrollment(program_number="83101", year=1),
            enrollment(program_number="83102", year=2),
        ],
    )
    candidate_course = course(
        "83103",
        [
            enrollment(program_number="99999", year=1),
            enrollment(program_number="83102", year=2),
        ],
    )

    result = evaluate_candidate(
        existing_course=existing_course,
        existing_date=date(2026, 1, 10),
        candidate_course=candidate_course,
        candidate_date=date(2026, 1, 11),
        k=3,
    )

    assert not result.accepted
    assert "program 83102 year 2" in result.explanation


def test_disabled_mandatory_gap_constraint_keeps_version_2_same_date_behavior_only() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_gap_days] = ThresholdConstraintSetting(
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

    schedules = generator.generate_for_period(
        courses=[
            course("83102", [enrollment()]),
            course("83103", [enrollment()]),
        ],
        exam_period=exam_period,
    )

    assert any(
        sorted(exam.exam_date for exam in schedule.scheduled_exams)
        == [date(2026, 1, 10), date(2026, 1, 11)]
        for schedule in schedules
    )


def test_enabled_mandatory_gap_constraint_rejects_close_dates_during_generation() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_gap_days] = ThresholdConstraintSetting(
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

    schedules = generator.generate_for_period(
        courses=[
            course("83102", [enrollment()]),
            course("83103", [enrollment()]),
        ],
        exam_period=exam_period,
    )

    assert schedules == []