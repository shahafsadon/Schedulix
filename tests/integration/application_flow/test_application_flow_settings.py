"""Integration tests for SchedulixApp.run(settings_path=...) (SCRUM-166).

These tests exercise the full CLI flow with an active Part 3 settings file:
reading courses/periods/programs, loading and validating constraint/ranking
settings via SchedulingSettingsFileReader (SCRUM-165), running the shared
SchedulingService (SCRUM-164), and writing ranked output with the Settings:
and Metrics: header/section lines (SCRUM-166).
"""
from pathlib import Path

from application.schedulixApp import SchedulixApp


ROOT = Path(__file__).resolve().parents[3]


def write_text_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def _courses_two_mandatory_same_program(tmp_path):
    """Two mandatory Exam courses, same program/year, FALL semester."""
    return write_text_file(
        tmp_path,
        "courses.txt",
        """
        $$$$
        Algorithms
        83110
        Dr. Ada
        83101,1,FALL,Obligatory
        Exam
        $$$$
        Calculus
        83120
        Dr. Newton
        83101,1,FALL,Obligatory
        Exam
        """,
    )


def _periods_two_dates(tmp_path):
    """A FALL Aleph period spanning two usable dates."""
    return write_text_file(
        tmp_path,
        "dates.txt",
        """
        $$$$
        FALL, Aleph
        01-02-2026, 02-02-2026
        """,
    )


def _programs_one(tmp_path):
    return write_text_file(tmp_path, "programs.txt", "83101")


def test_run_with_settings_file_applies_constraints_and_ranking(tmp_path):
    """A settings file enabling mandatory_gap_days and a ranking criterion
    is read, validated, applied to generation, and reflected in the output
    and ApplicationResult."""
    courses_path = _courses_two_mandatory_same_program(tmp_path)
    periods_path = _periods_two_dates(tmp_path)
    programs_path = _programs_one(tmp_path)
    output_path = tmp_path / "outputs" / "exam_schedules.txt"

    settings_path = write_text_file(
        tmp_path,
        "settings.txt",
        """
        mandatory_gap_days = on, 1
        any_course_gap_days = off, 0
        elective_conflicts_per_program = off, 0
        mandatory_span_days = off, 0
        max_exams_per_day = off, 0

        ranking: min_mandatory_gap
        """,
    )

    result = SchedulixApp().run(
        courses_path=courses_path,
        exam_periods_path=periods_path,
        programs_path=programs_path,
        output_path=output_path,
        settings_path=settings_path,
    )

    # Active settings are reported on the result.
    assert "mandatory_gap_days" in result.active_constraints
    assert "min_mandatory_gap" in result.active_ranking
    assert result.valid_system_count == result.schedule_count

    output = output_path.read_text(encoding="utf-8")

    # Header summarizes the active settings.
    assert "Settings:" in output
    assert "mandatory_gap_days=1" in output
    assert "min_mandatory_gap desc" in output
    assert f"Valid systems: {result.valid_system_count}" in output

    # Each schedule section has a Metrics: line.
    assert "Metrics:" in output

    # The exam-line format is unchanged.
    assert "Algorithms" in output
    assert "Calculus" in output
    assert "Dr. Ada" in output


def test_enabled_constraint_changes_the_set_of_valid_systems(tmp_path):
    """An enabled threshold constraint must actually affect generation, not
    just appear in the reported settings summary.

    Two mandatory courses share a (program, year); with two consecutive
    exam dates, both "no constraint" and "mandatory_gap_days = 1" runs
    produce systems (gap of 1 day satisfies k=1). Setting
    mandatory_gap_days = 2 makes it impossible for two exams one day apart
    to satisfy the constraint, so the valid-system count must drop to 0.
    """
    courses_path = _courses_two_mandatory_same_program(tmp_path)
    periods_path = _periods_two_dates(tmp_path)
    programs_path = _programs_one(tmp_path)

    # Baseline: no settings file, pre-Part-3 behavior.
    baseline_output_path = tmp_path / "outputs" / "baseline.txt"
    baseline = SchedulixApp().run(
        courses_path=courses_path,
        exam_periods_path=periods_path,
        programs_path=programs_path,
        output_path=baseline_output_path,
    )
    assert baseline.valid_system_count > 0

    # mandatory_gap_days = 2 with only two consecutive dates available makes
    # it impossible to satisfy the constraint for these two mandatory exams.
    settings_path = write_text_file(
        tmp_path,
        "settings_strict.txt",
        """
        mandatory_gap_days = on, 2
        any_course_gap_days = off, 0
        elective_conflicts_per_program = off, 0
        mandatory_span_days = off, 0
        max_exams_per_day = off, 0
        """,
    )
    constrained_output_path = tmp_path / "outputs" / "constrained.txt"
    constrained = SchedulixApp().run(
        courses_path=courses_path,
        exam_periods_path=periods_path,
        programs_path=programs_path,
        output_path=constrained_output_path,
        settings_path=settings_path,
    )

    assert constrained.valid_system_count == 0
    assert constrained.valid_system_count < baseline.valid_system_count

    constrained_output = constrained_output_path.read_text(encoding="utf-8")
    assert "Valid systems: 0" in constrained_output
    assert "mandatory_gap_days=2" in constrained_output

def test_run_without_settings_path_uses_pre_part3_defaults(tmp_path):
    """Omitting settings_path produces all-disabled constraints, no
    ranking, and a header with the explicit 'none' settings message."""
    courses_path = _courses_two_mandatory_same_program(tmp_path)
    periods_path = _periods_two_dates(tmp_path)
    programs_path = _programs_one(tmp_path)
    output_path = tmp_path / "outputs" / "exam_schedules.txt"

    result = SchedulixApp().run(
        courses_path=courses_path,
        exam_periods_path=periods_path,
        programs_path=programs_path,
        output_path=output_path,
    )

    assert result.active_constraints == []
    assert result.active_ranking == []

    output = output_path.read_text(encoding="utf-8")
    assert "Settings: none (all constraints disabled, no ranking)" in output
    assert "Metrics:" in output


def test_invalid_settings_file_raises_value_error(tmp_path):
    """A settings file with an enabled constraint and k=0 fails the shared
    SchedulingSettingsValidator (SCRUM-143) and raises before generation.

    The ValueError is raised by SchedulingSettingsFileReader.parse()
    (SCRUM-165) while SchedulixApp.run() loads the settings file — before
    SchedulingService.run() (SCRUM-164) is ever called. SchedulingService
    has its own re-validation of cache-read settings (covered separately by
    test_invalid_constraint_settings_raise_value_error in
    test_scheduling_service.py), but that path is not exercised here."""
    courses_path = _courses_two_mandatory_same_program(tmp_path)
    periods_path = _periods_two_dates(tmp_path)
    programs_path = _programs_one(tmp_path)
    output_path = tmp_path / "outputs" / "exam_schedules.txt"

    settings_path = write_text_file(
        tmp_path,
        "settings.txt",
        """
        mandatory_gap_days = on, 0
        """,
    )

    try:
        SchedulixApp().run(
            courses_path=courses_path,
            exam_periods_path=periods_path,
            programs_path=programs_path,
            output_path=output_path,
            settings_path=settings_path,
        )
    except ValueError as error:
        assert "mandatory_gap_days" in str(error).lower() or "k" in str(error).lower()
    else:
        raise AssertionError("Expected ValueError for invalid settings file")
