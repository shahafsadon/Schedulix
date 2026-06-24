import pytest
from pathlib import Path

from application.schedulixApp import SchedulixApp


ROOT = Path(__file__).resolve().parents[3]


def write_text_file(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_run_without_commands_path_is_unchanged(tmp_path) -> None:
    """run() without commands_path must behave identically to the original application flow."""
    output_path = tmp_path / "exam_schedules.txt"

    result = SchedulixApp().run(
        courses_path=ROOT / "data" / "examples" / "CourseExample.txt",
        exam_periods_path=ROOT / "data" / "examples" / "DatesExample.txt",
        programs_path=ROOT / "data" / "examples" / "ProgramsExample.txt",
        output_path=output_path,
        commands_path=None,
    )

    assert result.selected_program_count == 3
    assert result.total_course_count == 3
    assert result.relevant_course_count == 2
    assert result.exam_period_count == 3
    assert result.schedule_count > 0
    assert result.diff_report_path is None
    assert result.commands_executed == 0
    assert len(result.command_errors) == 0


def test_run_with_commands_path_executes_commands(tmp_path) -> None:
    """run() with commands_path must execute commands and output a diff_report.txt when COMPARE is run."""
    courses_path = write_text_file(
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
        83101,2,FALL,Obligatory
        Exam
        """,
    )
    periods_path = write_text_file(
        tmp_path,
        "dates.txt",
        """
        $$$$
        FALL, Aleph
        01-02-2026, 03-02-2026
        - 02-02-2026 Blocked
        """,
    )
    programs_path = write_text_file(tmp_path, "programs.txt", "83101")
    commands_path = write_text_file(
        tmp_path,
        "commands.txt",
        """
        SAVE_SNAPSHOT SnapA
        MOVE 83110 TO 03-02-2026
        SAVE_SNAPSHOT SnapB
        COMPARE SnapA SnapB
        """,
    )
    output_path = tmp_path / "exam_schedules.txt"

    result = SchedulixApp().run(
        courses_path=courses_path,
        exam_periods_path=periods_path,
        programs_path=programs_path,
        output_path=output_path,
        commands_path=commands_path,
    )

    assert result.commands_executed == 4
    assert len(result.command_errors) == 0, f"Errors: {result.command_errors}"
    assert result.diff_report_path is not None
    assert result.diff_report_path.exists()
    
    diff_content = result.diff_report_path.read_text(encoding="utf-8")
    assert "Snapshot Comparison Report" in diff_content
    assert "From: SnapA" in diff_content
    assert "To:   SnapB" in diff_content
    assert "Changed courses:" in diff_content
    assert "83110" in diff_content  # course that was moved


def test_run_with_invalid_command_raises_value_error(tmp_path) -> None:
    """Providing a commands file with a syntax/unrecognized command error must raise ValueError immediately."""
    courses_path = ROOT / "data" / "examples" / "CourseExample.txt"
    periods_path = ROOT / "data" / "examples" / "DatesExample.txt"
    programs_path = ROOT / "data" / "examples" / "ProgramsExample.txt"
    commands_path = write_text_file(
        tmp_path,
        "commands.txt",
        """
        SAVE_SNAPSHOT SnapA
        INVALID_COMMAND arg1
        """,
    )
    output_path = tmp_path / "exam_schedules.txt"

    with pytest.raises(ValueError) as context:
        SchedulixApp().run(
            courses_path=courses_path,
            exam_periods_path=periods_path,
            programs_path=programs_path,
            output_path=output_path,
            commands_path=commands_path,
        )
    
    assert "Line 2" in str(context.value)
    assert "Unrecognized command: 'INVALID_COMMAND'" in str(context.value)


def test_run_with_no_schedules_and_commands_returns_error(tmp_path) -> None:
    """If no schedules can be generated and commands are provided, a ValueError must be raised."""
    courses_path = write_text_file(
        tmp_path,
        "courses.txt",
        """
        $$$$
        Algorithms
        83110
        Dr. Ada
        83101,1,FALL,Obligatory
        Exam
        """,
    )
    periods_path = write_text_file(
        tmp_path,
        "dates.txt",
        """
        $$$$
        FALL, Aleph
        01-02-2026, 02-02-2026
        - 01-02-2026 Blocked
        - 02-02-2026 Blocked
        """,
    )
    programs_path = write_text_file(tmp_path, "programs.txt", "83101")
    commands_path = write_text_file(
        tmp_path,
        "commands.txt",
        "SAVE_SNAPSHOT SnapA",
    )
    output_path = tmp_path / "exam_schedules.txt"

    with pytest.raises(ValueError) as context:
        SchedulixApp().run(
            courses_path=courses_path,
            exam_periods_path=periods_path,
            programs_path=programs_path,
            output_path=output_path,
            commands_path=commands_path,
        )

    assert "No schedules were generated" in str(context.value)
