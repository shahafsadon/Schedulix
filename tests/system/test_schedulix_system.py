from pathlib import Path
import re
import time

from application.schedulixApp import (
    DEFAULT_COURSES_PATH,
    DEFAULT_EXAM_PERIODS_PATH,
    DEFAULT_PROGRAMS_PATH,
    SchedulixApp,
)
from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
from fileReader.fileTypeReaders.programReader import ProgramsFileReader
from scheduling.courseFilter import CourseFilter
from scheduling.examConflictDetector import ExamConflictDetector


DATE_LINE_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4} \| .+ \| .+$")
DATE_TOKEN_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")

REQUIRED_OUTPUT_HEADERS = [
    "Schedulix Exam Schedules",
    "Schedule ",
    "Semester:",
    "Moed:",
]

MAX_FULL_SYSTEM_SECONDS = 5.0


def run_example_system(tmp_path):
    output_path = tmp_path / "exam_schedules.txt"

    started_at = time.perf_counter()

    result = SchedulixApp().run(
        courses_path=DEFAULT_COURSES_PATH,
        exam_periods_path=DEFAULT_EXAM_PERIODS_PATH,
        programs_path=DEFAULT_PROGRAMS_PATH,
        output_path=output_path,
    )

    elapsed = time.perf_counter() - started_at

    return result, output_path, elapsed


def read_example_exam_course_names():
    selected_programs = ProgramsFileReader().read(DEFAULT_PROGRAMS_PATH)
    courses = CoursesFileReader().read(DEFAULT_COURSES_PATH)

    relevant_courses = CourseFilter().filter_relevant_courses(
        courses,
        selected_programs,
    )

    return {course.name.strip() for course in relevant_courses}


def output_exam_lines(output_text):
    return [
        line
        for line in output_text.splitlines()
        if DATE_LINE_PATTERN.match(line)
    ]


def test_full_system_run_with_example_files_creates_non_empty_output_file(tmp_path):
    result, output_path, _ = run_example_system(tmp_path)

    assert output_path.exists()
    assert output_path.is_file()
    assert output_path.stat().st_size > 0

    assert result.output_path == output_path
    assert result.selected_program_count > 0
    assert result.total_course_count > 0
    assert result.relevant_course_count > 0
    assert result.exam_period_count > 0
    assert result.schedule_count > 0


def test_full_system_output_schedules_only_exam_courses_from_selected_programs(tmp_path):
    _, output_path, _ = run_example_system(tmp_path)

    output = output_path.read_text(encoding="utf-8")
    allowed_exam_course_names = read_example_exam_course_names()

    scheduled_course_names = {
        line.split(" | ")[1].strip()
        for line in output_exam_lines(output)
    }

    assert scheduled_course_names
    assert scheduled_course_names <= allowed_exam_course_names
    assert "Software Project" not in scheduled_course_names


def test_full_system_output_format_is_readable_and_valid(tmp_path):
    result, output_path, _ = run_example_system(tmp_path)

    output = output_path.read_text(encoding="utf-8")
    lines = output.splitlines()
    exam_lines = output_exam_lines(output)

    assert output.endswith("\n")
    assert lines[0] == "Schedulix Exam Schedules"

    for required_header in REQUIRED_OUTPUT_HEADERS:
        assert required_header in output

    assert len(exam_lines) >= result.schedule_count

    for line in exam_lines:
        parts = [part.strip() for part in line.split(" | ")]

        assert len(parts) == 3
        assert DATE_TOKEN_PATTERN.match(parts[0])
        assert parts[1]
        assert parts[2]


def test_full_system_does_not_use_excluded_dates_from_example_periods(tmp_path):
    _, output_path, _ = run_example_system(tmp_path)

    output = output_path.read_text(encoding="utf-8")

    excluded_dates = {
        excluded_date.strftime("%d-%m-%Y")
        for period in ExamPeriodsFileReader().read(DEFAULT_EXAM_PERIODS_PATH)
        for excluded_date in period.excluded_dates
    }

    used_dates = {
        line.split(" | ")[0].strip()
        for line in output_exam_lines(output)
    }

    assert used_dates
    assert used_dates.isdisjoint(excluded_dates)


def test_full_system_generated_schedules_have_no_conflicts(tmp_path):
    output_path = tmp_path / "exam_schedules.txt"

    result = SchedulixApp().run(output_path=output_path)

    selected_programs = ProgramsFileReader().read(DEFAULT_PROGRAMS_PATH)
    courses = CoursesFileReader().read(DEFAULT_COURSES_PATH)
    exam_periods = ExamPeriodsFileReader().read(DEFAULT_EXAM_PERIODS_PATH)

    relevant_courses = CourseFilter().filter_relevant_courses(
        courses,
        selected_programs,
    )

    schedules = SchedulixApp().schedule_generator.generate_for_periods(
        relevant_courses,
        exam_periods,
    )

    assert len(schedules) == result.schedule_count

    assert all(
        ExamConflictDetector().is_valid_schedule(schedule.scheduled_exams)
        for schedule in schedules
    )


def test_full_system_run_finishes_within_required_time_limit(tmp_path):
    _, _, elapsed = run_example_system(tmp_path)

    assert elapsed < MAX_FULL_SYSTEM_SECONDS