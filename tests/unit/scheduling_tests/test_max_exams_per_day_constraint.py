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
    MaxExamsPerDayConstraint,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamScheduleGenerator


def course(
    number: str,
    program_number: str = "83101",
    year: int = 1,
    status: str = "Elective",
) -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment(
                program_number=program_number,
                year=year,
                semester="FALL",
                status=status,
            )
        ],
        evaluation_type="Exam",
    )


def evaluate_candidate(
    existing_exams: list[ScheduledExam],
    candidate_course: Course,
    candidate_date: date,
    k: int,
):
    return MaxExamsPerDayConstraint(k=k).evaluate(
        ConstraintEvaluationContext(
            candidate_exam=candidate_course,
            candidate_date=candidate_date,
            partial_schedule=existing_exams,
        )
    )


def test_rejects_candidate_when_date_would_exceed_configured_limit() -> None:
    existing_exams = [
        ScheduledExam(course("83102"), date(2026, 1, 10)),
        ScheduledExam(course("83103", program_number="83102"), date(2026, 1, 10)),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83104", program_number="83103"),
        candidate_date=date(2026, 1, 10),
        k=2,
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.5"
    assert "Date 2026-01-10 has 3 exams" in result.explanation
    assert "maximum allowed is 2" in result.explanation


def test_accepts_candidate_when_date_contains_exactly_k_exams() -> None:
    existing_exams = [
        ScheduledExam(course("83102"), date(2026, 1, 10)),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83103", program_number="83102"),
        candidate_date=date(2026, 1, 10),
        k=2,
    )

    assert result.accepted


def test_accepts_candidate_when_date_remains_below_k() -> None:
    existing_exams = [
        ScheduledExam(course("83102"), date(2026, 1, 10)),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83103", program_number="83102"),
        candidate_date=date(2026, 1, 11),
        k=2,
    )

    assert result.accepted


def test_counts_total_exams_across_all_selected_programs() -> None:
    existing_exams = [
        ScheduledExam(course("83102", program_number="83101"), date(2026, 1, 10)),
        ScheduledExam(course("83103", program_number="83102"), date(2026, 1, 10)),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83104", program_number="83103"),
        candidate_date=date(2026, 1, 10),
        k=2,
    )

    assert not result.accepted


def test_same_physical_course_with_multiple_program_rows_counts_as_one_exam() -> None:
    multi_program_course = Course(
        name="Multi Program Course",
        course_number="83102",
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment("83101", 1, "FALL", "Elective"),
            ProgramEnrollment("83102", 2, "FALL", "Elective"),
            ProgramEnrollment("83103", 3, "FALL", "Elective"),
        ],
        evaluation_type="Exam",
    )

    result = evaluate_candidate(
        existing_exams=[
            ScheduledExam(multi_program_course, date(2026, 1, 10)),
        ],
        candidate_course=course("83103", program_number="99999"),
        candidate_date=date(2026, 1, 10),
        k=2,
    )

    assert result.accepted


def test_constraint_uses_indexed_exam_count_when_available() -> None:
    result = MaxExamsPerDayConstraint(k=2).evaluate(
        ConstraintEvaluationContext(
            candidate_exam=course("83104"),
            candidate_date=date(2026, 1, 10),
            partial_schedule=[],
            metadata={
                "exam_counts_by_date": {
                    date(2026, 1, 10): 2,
                }
            },
        )
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.5"
    assert "has 3 exams" in result.explanation


def test_disabled_max_exams_per_day_constraint_does_not_affect_generation() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = ThresholdConstraintSetting(
        enabled=False,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_registry=ConstraintRegistry.default(settings)
    )
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 10),
        excluded_dates=[],
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=exam_period,
    )

    assert len(schedules) == 1
    assert len(schedules[0].scheduled_exams) == 2


def test_enabled_max_exams_per_day_constraint_rejects_invalid_generation_branch() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = ThresholdConstraintSetting(
        enabled=True,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_registry=ConstraintRegistry.default(settings)
    )
    exam_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 10),
        excluded_dates=[],
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=exam_period,
    )

    assert schedules == []


def test_counter_state_remains_correct_after_backtracking() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = ThresholdConstraintSetting(
        enabled=True,
        k=1,
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
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=exam_period,
    )

    assert len(schedules) == 2

    for schedule in schedules:
        dates = [exam.exam_date for exam in schedule.scheduled_exams]
        assert date(2026, 1, 10) in dates
        assert date(2026, 1, 11) in dates


def test_rule_supports_every_relevant_exam_period() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = ThresholdConstraintSetting(
        enabled=True,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_registry=ConstraintRegistry.default(settings)
    )
    fall_period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 10),
        excluded_dates=[],
    )
    spring_period = ExamPeriod(
        semester="SPRING",
        moed="Aleph",
        start_date=date(2026, 2, 10),
        end_date=date(2026, 2, 10),
        excluded_dates=[],
    )

    fall_course_1 = course("83102", program_number="83101", status="Elective")
    fall_course_2 = course("83103", program_number="83102", status="Elective")

    spring_course_1 = Course(
        name="Course 83104",
        course_number="83104",
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment("83103", 1, "SPRING", "Elective"),
        ],
        evaluation_type="Exam",
    )
    spring_course_2 = Course(
        name="Course 83105",
        course_number="83105",
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment("83104", 1, "SPRING", "Elective"),
        ],
        evaluation_type="Exam",
    )

    systems = list(
        generator.iter_exam_systems(
            courses=[
                fall_course_1,
                fall_course_2,
                spring_course_1,
                spring_course_2,
            ],
            exam_periods=[
                fall_period,
                spring_period,
            ],
        )
    )

    assert systems == []