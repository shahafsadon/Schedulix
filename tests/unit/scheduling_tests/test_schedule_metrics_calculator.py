from __future__ import annotations

from datetime import date

import pytest

from models import Course, ProgramEnrollment
from ranking_settings import MISSING_METRIC_VALUE
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.scheduleMetricsCalculator import ScheduleMetricsCalculator


def course(
    name: str,
    number: str,
    enrollments: list[tuple[str, int, str, str]],
) -> Course:
    """Create a course with explicit program/year/status rows."""
    return Course(
        name=name,
        course_number=number,
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment(
                program_number,
                year,
                semester,
                status,
            )
            for program_number, year, semester, status in enrollments
        ],
        evaluation_type="Exam",
    )


def exam(
    exam_course: Course,
    exam_date: date,
) -> ScheduledExam:
    """Create one scheduled exam."""
    return ScheduledExam(
        course=exam_course,
        exam_date=exam_date,
    )


def system(
    scheduled_exams: list[ScheduledExam],
    semester: str = "FALL",
    moed: str = "Aleph",
) -> ExamSystem:
    """Create a one-period exam system."""
    return ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester=semester,
                moed=moed,
                scheduled_exams=scheduled_exams,
            )
        ]
    )


def test_empty_system_uses_documented_missing_values() -> None:
    """An empty system has no eligible pairs or date groups."""
    metrics = ScheduleMetricsCalculator().calculate(
        ExamSystem(period_schedules=[]),
        schedule_id=7,
    )

    assert metrics.schedule_id == 7
    assert metrics.min_mandatory_gap == MISSING_METRIC_VALUE
    assert metrics.average_all_gap == MISSING_METRIC_VALUE
    assert metrics.elective_collision_count == 0
    assert metrics.mandatory_span == MISSING_METRIC_VALUE
    assert metrics.max_exams_per_day == MISSING_METRIC_VALUE


def test_single_exam_has_max_day_count_but_no_pair_metrics() -> None:
    """A single exam can be counted by date but cannot form a gap/span pair."""
    physics = course(
        "Physics",
        "83102",
        [("83101", 1, "FALL", "Obligatory")],
    )

    metrics = ScheduleMetricsCalculator().calculate(
        system([exam(physics, date(2026, 1, 1))]),
        schedule_id=1,
    )

    assert metrics.min_mandatory_gap == MISSING_METRIC_VALUE
    assert metrics.average_all_gap == MISSING_METRIC_VALUE
    assert metrics.elective_collision_count == 0
    assert metrics.mandatory_span == MISSING_METRIC_VALUE
    assert metrics.max_exams_per_day == 1


def test_calculates_mandatory_gap_average_gap_and_span() -> None:
    """Program/year pairs drive the gap metrics."""
    first = course(
        "Algorithms",
        "83110",
        [("83101", 2, "FALL", "Obligatory")],
    )
    second = course(
        "Calculus",
        "83120",
        [("83101", 2, "FALL", "Obligatory")],
    )
    elective = course(
        "Art",
        "83130",
        [("83101", 2, "FALL", "Elective")],
    )

    metrics = ScheduleMetricsCalculator().calculate(
        system(
            [
                exam(first, date(2026, 1, 1)),
                exam(elective, date(2026, 1, 3)),
                exam(second, date(2026, 1, 5)),
            ]
        ),
        schedule_id=1,
    )

    assert metrics.min_mandatory_gap == 4
    assert metrics.average_all_gap == pytest.approx(8 / 3)
    assert metrics.mandatory_span == 4
    assert metrics.max_exams_per_day == 1


def test_multi_program_course_contributes_to_each_program_year_bucket() -> None:
    """A cross-listed course participates in every represented bucket."""
    cross_listed = course(
        "Cross Listed",
        "83140",
        [
            ("83101", 1, "FALL", "Obligatory"),
            ("83108", 2, "FALL", "Obligatory"),
        ],
    )
    shared_program = course(
        "Shared Program",
        "83141",
        [("83108", 2, "FALL", "Obligatory")],
    )

    metrics = ScheduleMetricsCalculator().calculate(
        system(
            [
                exam(cross_listed, date(2026, 1, 1)),
                exam(shared_program, date(2026, 1, 4)),
            ]
        ),
        schedule_id=1,
    )

    assert metrics.min_mandatory_gap == 3
    assert metrics.average_all_gap == 3


def test_elective_collisions_count_same_date_shared_program_pairs() -> None:
    """Only same-date elective/elective pairs in a shared program are counted."""
    first = course(
        "Elective A",
        "83200",
        [("83101", 1, "FALL", "Elective")],
    )
    second = course(
        "Elective B",
        "83201",
        [("83101", 3, "FALL", "Elective")],
    )
    third = course(
        "Other Program",
        "83202",
        [("83108", 1, "FALL", "Elective")],
    )

    metrics = ScheduleMetricsCalculator().calculate(
        system(
            [
                exam(first, date(2026, 1, 1)),
                exam(second, date(2026, 1, 1)),
                exam(third, date(2026, 1, 1)),
            ]
        ),
        schedule_id=1,
    )

    assert metrics.elective_collision_count == 1
    assert metrics.max_exams_per_day == 3


def test_elective_status_is_normalized_and_mandatory_row_wins() -> None:
    """Elective text is normalized, but mandatory enrollment stays stricter."""
    elective_a = course(
        "Elective A",
        "83210",
        [("83101", 1, "FALL", " elective ")],
    )
    elective_b = course(
        "Elective B",
        "83211",
        [("83101", 1, "FALL", "ELECTIVE")],
    )
    mixed_status = course(
        "Mixed Status",
        "83212",
        [
            ("83101", 1, "FALL", "Elective"),
            ("83101", 1, "FALL", "Obligatory"),
        ],
    )

    metrics = ScheduleMetricsCalculator().calculate(
        system(
            [
                exam(elective_a, date(2026, 1, 1)),
                exam(elective_b, date(2026, 1, 1)),
                exam(mixed_status, date(2026, 1, 1)),
            ]
        ),
        schedule_id=1,
    )

    assert metrics.elective_collision_count == 1
    assert metrics.min_mandatory_gap == MISSING_METRIC_VALUE


def test_mandatory_span_is_calculated_per_semester_and_moed_group() -> None:
    """Bet exams do not inflate the Aleph mandatory span group."""
    first = course(
        "Aleph A",
        "83300",
        [("83101", 1, "FALL", "Obligatory")],
    )
    second = course(
        "Aleph B",
        "83301",
        [("83101", 1, "FALL", "Obligatory")],
    )
    third = course(
        "Bet A",
        "83302",
        [("83101", 1, "FALL", "Obligatory")],
    )
    fourth = course(
        "Bet B",
        "83303",
        [("83101", 1, "FALL", "Obligatory")],
    )

    exam_system = ExamSystem(
        period_schedules=[
            ExamSchedule(
                "FALL",
                "Aleph",
                [
                    exam(first, date(2026, 1, 1)),
                    exam(second, date(2026, 1, 5)),
                ],
            ),
            ExamSchedule(
                "FALL",
                "Bet",
                [
                    exam(third, date(2026, 4, 10)),
                    exam(fourth, date(2026, 4, 12)),
                ],
            ),
        ]
    )

    metrics = ScheduleMetricsCalculator().calculate(
        exam_system,
        schedule_id=1,
    )

    assert metrics.mandatory_span == 4
