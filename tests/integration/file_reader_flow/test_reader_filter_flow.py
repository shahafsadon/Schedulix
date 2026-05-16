from datetime import date

from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
from fileReader.fileTypeReaders.programReader import ProgramsFileReader
from scheduling.courseFilter import CourseFilter
from scheduling.examDateHandler import ExamDateHandler


def write_text_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


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
    assert [p.program_number for p in relevant_courses[0].programs] == [
        "83101",
        "83102",
    ]
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
