from pathlib import Path

from application.schedulixApp import SchedulixApp


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "data" / "examples" / "basic_course_example"


def write_text_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_app_run_with_repository_examples_writes_output_file(tmp_path):
    output_path = tmp_path / "exam_schedules.txt"

    result = SchedulixApp().run(
        courses_path=EXAMPLES / "courses.txt",
        exam_periods_path=EXAMPLES / "dates.txt",
        programs_path=EXAMPLES / "programs.txt",
        output_path=output_path,
    )

    output_text = output_path.read_text(encoding="utf-8")

    assert result.selected_program_count == 3
    assert result.total_course_count == 3
    assert result.relevant_course_count == 2
    assert result.exam_period_count == 3
    assert result.schedule_count > 0
    assert output_path.exists()
    assert "Schedulix Exam Schedules" in output_text
    assert "Schedule 1" in output_text
    assert "Semester: FALL" in output_text
    assert "Moed: Aleph" in output_text


def test_full_application_flow_reads_filters_schedules_and_writes_output(tmp_path):
    courses_path = write_text_file(
        tmp_path,
        "courses.txt",
        """
        $$$$
        Algorithms
        83110
        Dr. Ada
        83101,2,FALL,Obligatory
        Exam
        $$$$
        Calculus
        83120
        Dr. Newton
        83101,2,FALL,Obligatory
        Exam
        $$$$
        Studio
        83130
        Dr. Builder
        83101,2,FALL,Obligatory
        Project
        $$$$
        Physics
        83140
        Dr. Feynman
        83102,2,FALL,Obligatory
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
    output_path = tmp_path / "outputs" / "exam_schedules.txt"

    result = SchedulixApp().run(
        courses_path=courses_path,
        exam_periods_path=periods_path,
        programs_path=programs_path,
        output_path=output_path,
    )

    output = output_path.read_text(encoding="utf-8")
    assert result.selected_program_count == 1
    assert result.total_course_count == 4
    assert result.relevant_course_count == 2
    assert result.exam_period_count == 1
    assert result.schedule_count == 2
    assert result.output_path == output_path
    assert "Algorithms" in output
    assert "Calculus" in output
    assert "Studio" not in output
    assert "Physics" not in output
    assert "02-02-2026" not in output
