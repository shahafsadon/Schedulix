from datetime import date

import pytest

from application.schedulixApp import SchedulixApp
from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
from fileReader.fileTypeReaders.programReader import ProgramsFileReader
from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.courseFilter import CourseFilter
from scheduling.examConflictDetector import ExamConflictDetector, ScheduledExam
from scheduling.examDateHandler import ExamDateHandler
from scheduling.examScheduleGenerator import ExamScheduleGenerator


def write_text_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def enrollment(program="83101", year=1, semester="FALL", status="Obligatory"):
    return ProgramEnrollment(
        program_number=program,
        year=year,
        semester=semester,
        status=status,
    )


def course(
    name,
    number,
    programs,
    evaluation_type="Exam",
    instructor="Dr. Test",
):
    return Course(
        name=name,
        course_number=number,
        instructor=instructor,
        programs=programs,
        evaluation_type=evaluation_type,
    )


def test_course_and_program_readers_feed_course_filter_with_only_selected_exam_courses(tmp_path):
    courses_path = write_text_file(
        tmp_path,
        "courses.txt",
        """
        $$$$
        Algorithms
        83110
        Dr. Ada
        83101,2,FALL,Obligatory
        83102,2,FALL,Elective
        Exam
        $$$$
        Product Workshop
        83120
        Dr. Grace
        83101,2,FALL,Obligatory
        Project
        $$$$
        Databases
        83130
        Dr. Codd
        83103,2,FALL,Obligatory
        Exam
        """,
    )
    programs_path = write_text_file(tmp_path, "programs.txt", "83101, 83102")

    courses = CoursesFileReader().read(courses_path)
    selected_programs = ProgramsFileReader().read(programs_path)

    relevant_courses = CourseFilter().filter_relevant_courses(courses, selected_programs)

    assert [c.course_number for c in relevant_courses] == ["83110"]
    assert [p.program_number for p in relevant_courses[0].programs] == ["83101", "83102"]
    assert relevant_courses[0].evaluation_type == "Exam"


def test_exam_period_reader_feeds_date_handler_and_expands_excluded_date_ranges(tmp_path):
    periods_path = write_text_file(
        tmp_path,
        "dates.txt",
        """
        $$$$
        FALL, Aleph
        01-02-2026, 05-02-2026
        - 02-02-2026 Maintenance
        - 04-02-2026, 05-02-2026 Holiday
        """,
    )

    periods = ExamPeriodsFileReader().read(periods_path)
    valid_dates = ExamDateHandler().get_valid_dates(periods[0])

    assert periods[0].excluded_dates == [
        date(2026, 2, 2),
        date(2026, 2, 4),
        date(2026, 2, 5),
    ]
    assert valid_dates == [date(2026, 2, 1), date(2026, 2, 3)]


def test_schedule_generation_uses_conflict_detector_to_reject_same_day_mandatory_conflicts():
    courses = [
        course("Algorithms", "83110", [enrollment(status="Obligatory")]),
        course("Calculus", "83120", [enrollment(status="Elective")]),
    ]
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
    )

    schedules = ExamScheduleGenerator().generate_for_period(courses, period)

    assert len(schedules) == 2
    for schedule in schedules:
        assert {exam.course.course_number for exam in schedule.scheduled_exams} == {"83110", "83120"}
        assert len({exam.exam_date for exam in schedule.scheduled_exams}) == 2
        assert ExamConflictDetector().is_valid_schedule(schedule.scheduled_exams)


def test_schedule_generation_allows_same_day_only_when_shared_program_year_courses_are_both_elective():
    courses = [
        course("AI", "83140", [enrollment(status="Elective")]),
        course("Graphics", "83150", [enrollment(status="Elective")]),
    ]
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )

    schedules = ExamScheduleGenerator().generate_for_period(courses, period)

    assert len(schedules) == 1
    assert [exam.exam_date for exam in schedules[0].scheduled_exams] == [
        date(2026, 2, 1),
        date(2026, 2, 1),
    ]


def test_filtered_exam_courses_are_passed_into_scheduler_without_unselected_program_rows():
    selected_programs = ["83101"]
    courses = [
        course(
            "Algorithms",
            "83110",
            [
                enrollment(program="83101", year=2, semester="FALL"),
                enrollment(program="83199", year=2, semester="FALL"),
            ],
        ),
        course("Seminar", "83190", [enrollment(program="83101")], evaluation_type="Attendance"),
    ]
    filtered = CourseFilter().filter_relevant_courses(courses, selected_programs)
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )

    schedules = ExamScheduleGenerator().generate_for_period(filtered, period)

    assert len(schedules) == 1
    scheduled_course = schedules[0].scheduled_exams[0].course
    assert scheduled_course.course_number == "83110"
    assert [p.program_number for p in scheduled_course.programs] == ["83101"]


def test_excluded_dates_are_never_used_by_generated_schedules():
    courses = [course("Algorithms", "83110", [enrollment()])]
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 3),
        excluded_dates=[date(2026, 2, 2)],
    )

    schedules = ExamScheduleGenerator().generate_for_period(courses, period)
    scheduled_dates = {schedule.scheduled_exams[0].exam_date for schedule in schedules}

    assert scheduled_dates == {date(2026, 2, 1), date(2026, 2, 3)}
    assert date(2026, 2, 2) not in scheduled_dates


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


def test_no_schedule_is_generated_when_conflicting_courses_have_only_one_available_date():
    courses = [
        course("Algorithms", "83110", [enrollment(status="Obligatory")]),
        course("Calculus", "83120", [enrollment(status="Obligatory")]),
    ]
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )

    schedules = ExamScheduleGenerator().generate_for_period(courses, period)

    assert schedules == []


def test_generator_schedules_only_courses_matching_the_exam_period_semester():
    courses = [
        course("Fall Course", "83110", [enrollment(semester="FALL")]),
        course("Spring Course", "83120", [enrollment(semester="SPRI")]),
    ]
    period = ExamPeriod(
        semester="SPRI",
        moed="Aleph",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    schedules = ExamScheduleGenerator().generate_for_period(courses, period)

    assert len(schedules) == 1
    assert [exam.course.name for exam in schedules[0].scheduled_exams] == ["Spring Course"]