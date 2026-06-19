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
    ElectiveConflictsPerProgramConstraint,
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
    semester: str = "FALL",
    status: str = "Elective",
) -> ProgramEnrollment:
    return ProgramEnrollment(
        program_number=program_number,
        year=year,
        semester=semester,
        status=status,
    )


def evaluate_candidate(
    existing_exams: list[ScheduledExam],
    candidate_course: Course,
    candidate_date: date,
    k: int,
):
    return ElectiveConflictsPerProgramConstraint(k=k).evaluate(
        ConstraintEvaluationContext(
            candidate_exam=candidate_course,
            candidate_date=candidate_date,
            partial_schedule=existing_exams,
        )
    )


def test_rejects_schedule_when_one_program_exceeds_configured_limit() -> None:
    existing_exams = [
        ScheduledExam(
            course("83102", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
        ScheduledExam(
            course("83103", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83104", [enrollment(program_number="83101")]),
        candidate_date=date(2026, 1, 10),
        k=2,
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.3"
    assert "Program 83101" in result.explanation
    assert "maximum allowed is 2" in result.explanation


def test_accepts_schedule_when_collision_count_equals_configured_limit() -> None:
    existing_exams = [
        ScheduledExam(
            course("83102", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83103", [enrollment(program_number="83101")]),
        candidate_date=date(2026, 1, 10),
        k=1,
    )

    assert result.accepted


def test_k_zero_rejects_any_elective_same_date_collision() -> None:
    existing_exams = [
        ScheduledExam(
            course("83102", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83103", [enrollment(program_number="83101")]),
        candidate_date=date(2026, 1, 10),
        k=0,
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.3"
    assert "Program 83101 has 1 elective same-date collisions" in result.explanation


def test_different_programs_maintain_separate_collision_counters() -> None:
    existing_exams = [
        ScheduledExam(
            course("83102", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
        ScheduledExam(
            course("83103", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83104", [enrollment(program_number="83102")]),
        candidate_date=date(2026, 1, 10),
        k=1,
    )

    assert result.accepted


def test_different_dates_do_not_create_elective_collisions() -> None:
    existing_exams = [
        ScheduledExam(
            course("83102", [enrollment(program_number="83101")]),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83103", [enrollment(program_number="83101")]),
        candidate_date=date(2026, 1, 11),
        k=0,
    )

    assert result.accepted


def test_mandatory_course_does_not_count_as_elective_collision() -> None:
    existing_exams = [
        ScheduledExam(
            course("83102", [enrollment(program_number="83101", status="Obligatory")]),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course("83103", [enrollment(program_number="83101", status="Elective")]),
        candidate_date=date(2026, 1, 10),
        k=0,
    )

    assert result.accepted


def test_mandatory_course_conflicts_still_follow_existing_version_2_rule() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.elective_conflicts_per_program] = (
        ThresholdConstraintSetting(
            enabled=True,
            k=10,
        )
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
            course("83102", [enrollment(program_number="83101", status="Obligatory")]),
            course("83103", [enrollment(program_number="83101", status="Elective")]),
        ],
        exam_period=exam_period,
    )

    assert schedules == []


def test_multiple_program_course_adds_collision_to_each_shared_elective_program() -> None:
    existing_exams = [
        ScheduledExam(
            course(
                "83102",
                [
                    enrollment(program_number="83101"),
                    enrollment(program_number="83102"),
                ],
            ),
            date(2026, 1, 10),
        ),
    ]

    result = evaluate_candidate(
        existing_exams=existing_exams,
        candidate_course=course(
            "83103",
            [
                enrollment(program_number="83101"),
                enrollment(program_number="83102"),
            ],
        ),
        candidate_date=date(2026, 1, 10),
        k=0,
    )

    assert not result.accepted
    assert result.violated_requirement == "Req 2.3"
    assert (
        "Program 83101" in result.explanation
        or "Program 83102" in result.explanation
    )


def test_disabled_elective_collision_constraint_keeps_version_2_behavior_for_elective_pairs() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.elective_conflicts_per_program] = (
        ThresholdConstraintSetting(
            enabled=False,
            k=0,
        )
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
            course("83102", [enrollment(program_number="83101", status="Elective")]),
            course("83103", [enrollment(program_number="83101", status="Elective")]),
        ],
        exam_period=exam_period,
    )

    assert len(schedules) == 1


def test_enabled_elective_collision_constraint_rejects_invalid_candidate_during_generation() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.elective_conflicts_per_program] = (
        ThresholdConstraintSetting(
            enabled=True,
            k=0,
        )
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
            course("83102", [enrollment(program_number="83101", status="Elective")]),
            course("83103", [enrollment(program_number="83101", status="Elective")]),
        ],
        exam_period=exam_period,
    )

    assert schedules == []


def test_backtracking_restores_collision_state_and_finds_later_valid_schedule() -> None:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.elective_conflicts_per_program] = (
        ThresholdConstraintSetting(
            enabled=True,
            k=0,
        )
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
            course("83102", [enrollment(program_number="83101", status="Elective")]),
            course("83103", [enrollment(program_number="83101", status="Elective")]),
        ],
        exam_period=exam_period,
    )

    assert len(schedules) == 2

    for schedule in schedules:
        dates = [exam.exam_date for exam in schedule.scheduled_exams]
        assert date(2026, 1, 10) in dates
        assert date(2026, 1, 11) in dates