from __future__ import annotations

from datetime import date
from pathlib import Path

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.examScheduleGenerator import ExamScheduleGenerator


def course(
    number: str,
    program_number: str = "83101",
    year: int = 1,
    semester: str = "FALL",
    status: str = "Obligatory",
) -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment(
                program_number=program_number,
                year=year,
                semester=semester,
                status=status,
            )
        ],
        evaluation_type="Exam",
    )


def period(
    start_date: date,
    end_date: date,
    semester: str = "FALL",
    moed: str = "Aleph",
) -> ExamPeriod:
    return ExamPeriod(
        semester=semester,
        moed=moed,
        start_date=start_date,
        end_date=end_date,
        excluded_dates=[],
    )


def settings_with_only(
    constraint_type: ThresholdConstraintType,
    k: int,
) -> SchedulingConstraintSettings:
    settings = SchedulingConstraintSettings.default_configuration()

    for current_type in ThresholdConstraintType:
        settings.constraints[current_type] = ThresholdConstraintSetting(
            enabled=False,
            k=0,
        )

    settings.constraints[constraint_type] = ThresholdConstraintSetting(
        enabled=True,
        k=k,
    )

    return settings


def test_generator_accepts_constraint_settings_directly() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.max_exams_per_day,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 10),
        ),
    )

    assert schedules == []


def test_mandatory_gap_requirement_affects_generated_results() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.mandatory_gap_days,
        k=3,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", status="Obligatory"),
            course("83103", status="Obligatory"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 11),
        ),
    )

    assert schedules == []


def test_general_gap_requirement_affects_generated_results() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.any_course_gap_days,
        k=3,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", status="Elective"),
            course("83103", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 11),
        ),
    )

    assert schedules == []


def test_elective_collision_requirement_affects_generated_results() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.elective_conflicts_per_program,
        k=0,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", status="Elective"),
            course("83103", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 10),
        ),
    )

    assert schedules == []


def test_mandatory_span_requirement_filters_complete_systems_before_yielding() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.mandatory_span_days,
        k=3,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    systems = list(
        generator.iter_exam_systems(
            courses=[
                course("83102", status="Obligatory"),
                course("83103", status="Obligatory"),
            ],
            exam_periods=[
                period(
                    date(2026, 1, 10),
                    date(2026, 1, 11),
                )
            ],
        )
    )

    assert systems == []


def test_max_exams_per_day_requirement_affects_generated_results() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.max_exams_per_day,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 10),
        ),
    )

    assert schedules == []


def test_disabled_threshold_constraints_preserve_version_2_generation_behavior() -> None:
    settings = SchedulingConstraintSettings.default_configuration()

    for constraint_type in ThresholdConstraintType:
        settings.constraints[constraint_type] = ThresholdConstraintSetting(
            enabled=False,
            k=0,
        )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", status="Elective"),
            course("83103", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 10),
        ),
    )

    assert len(schedules) == 1
    assert len(schedules[0].scheduled_exams) == 2


def test_diagnostic_counters_track_generated_accepted_and_pruned_candidates() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.max_exams_per_day,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    schedules = generator.generate_for_period(
        courses=[
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 10),
        ),
    )

    assert schedules == []
    assert generator.diagnostics.generated_candidates == 2
    assert generator.diagnostics.accepted_candidates == 1
    assert generator.diagnostics.pruned_candidates == 1
    assert (
        generator.diagnostics.generated_candidates
        == generator.diagnostics.accepted_candidates
        + generator.diagnostics.pruned_candidates
    )


def test_diagnostic_counters_can_be_reset() -> None:
    settings = settings_with_only(
        ThresholdConstraintType.max_exams_per_day,
        k=1,
    )

    generator = ExamScheduleGenerator(
        constraint_settings=settings,
    )

    generator.generate_for_period(
        courses=[
            course("83102", program_number="83101", status="Elective"),
            course("83103", program_number="83102", status="Elective"),
        ],
        exam_period=period(
            date(2026, 1, 10),
            date(2026, 1, 10),
        ),
    )

    assert generator.diagnostics.generated_candidates > 0

    generator.reset_diagnostics()

    assert generator.diagnostics.generated_candidates == 0
    assert generator.diagnostics.accepted_candidates == 0
    assert generator.diagnostics.pruned_candidates == 0


def test_generator_does_not_import_gui_presenter_or_file_dialog_modules() -> None:
    generator_source = Path(
        "src/scheduling/examScheduleGenerator.py"
    ).read_text(
        encoding="utf-8",
    )

    forbidden_import_fragments = [
        "customtkinter",
        "tkinter",
        "filedialog",
        "gui.",
        "presenter",
        "Presenter",
    ]

    for fragment in forbidden_import_fragments:
        assert fragment not in generator_source