import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FILE_READER = SRC / "fileReader"

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(FILE_READER))

from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.examScheduleGenerator import ExamScheduleGenerator


def make_course(
    name: str,
    course_number: str,
    program_number: str,
    year: int,
    semester: str,
    status: str,
) -> Course:
    """Create a Course object for schedule generator tests."""
    return Course(
        name=name,
        course_number=course_number,
        instructor="Test Instructor",
        programs=[ProgramEnrollment(program_number, year, semester, status)],
        evaluation_type="Exam",
    )


def make_period(start_date: date, end_date: date) -> ExamPeriod:
    """Create a FALL Aleph exam period for tests."""
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=start_date,
        end_date=end_date,
        excluded_dates=[],
    )


class ExamScheduleGeneratorTests(unittest.TestCase):
    """Tests for generating valid exam schedule options."""

    def test_generates_one_schedule_for_each_possible_single_course_date(self) -> None:
        """A single course can be assigned to each valid date in the period."""
        course = make_course("Physics 1", "83102", "83101", 1, "FALL", "Obligatory")
        period = make_period(date(2026, 1, 1), date(2026, 1, 2))

        schedules = ExamScheduleGenerator().generate_for_period([course], period)

        self.assertEqual(len(schedules), 2)
        self.assertEqual(
            [schedule.scheduled_exams[0].exam_date for schedule in schedules],
            [date(2026, 1, 1), date(2026, 1, 2)],
        )

    def test_keeps_only_schedules_without_required_course_conflicts(self) -> None:
        """Required courses in the same program year cannot share a date."""
        first_course = make_course(
            "Physics 1",
            "83102",
            "83101",
            1,
            "FALL",
            "Obligatory",
        )
        second_course = make_course(
            "Calculus 1",
            "83112",
            "83101",
            1,
            "FALL",
            "Obligatory",
        )
        period = make_period(date(2026, 1, 1), date(2026, 1, 2))

        schedules = ExamScheduleGenerator().generate_for_period(
            [first_course, second_course],
            period,
        )

        self.assertEqual(len(schedules), 2)
        for schedule in schedules:
            first_date = schedule.scheduled_exams[0].exam_date
            second_date = schedule.scheduled_exams[1].exam_date
            self.assertNotEqual(first_date, second_date)

    def test_allows_same_date_for_two_elective_courses(self) -> None:
        """Two elective courses may share the same date."""
        first_course = make_course(
            "Elective A",
            "83120",
            "83101",
            2,
            "FALL",
            "Elective",
        )
        second_course = make_course(
            "Elective B",
            "83121",
            "83101",
            2,
            "FALL",
            "Elective",
        )
        period = make_period(date(2026, 1, 1), date(2026, 1, 1))

        schedules = ExamScheduleGenerator().generate_for_period(
            [first_course, second_course],
            period,
        )

        self.assertEqual(len(schedules), 1)
        self.assertEqual(
            [exam.exam_date for exam in schedules[0].scheduled_exams],
            [date(2026, 1, 1), date(2026, 1, 1)],
        )

    def test_uses_only_courses_from_the_exam_period_semester(self) -> None:
        """A FALL period should not schedule a SPRI course."""
        fall_course = make_course(
            "Physics 1",
            "83102",
            "83101",
            1,
            "FALL",
            "Obligatory",
        )
        spring_course = make_course(
            "Software Project",
            "83533",
            "83101",
            3,
            "SPRI",
            "Elective",
        )
        period = make_period(date(2026, 1, 1), date(2026, 1, 1))

        schedules = ExamScheduleGenerator().generate_for_period(
            [fall_course, spring_course],
            period,
        )

        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0].scheduled_exams[0].course.name, "Physics 1")

    def test_generates_complete_exam_systems_across_relevant_periods(self) -> None:
        """One full system should combine one valid option from each period."""
        course = make_course("Physics 1", "83102", "83101", 1, "FALL", "Obligatory")
        periods = [
            ExamPeriod(
                semester="FALL",
                moed="Aleph",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
                excluded_dates=[],
            ),
            ExamPeriod(
                semester="FALL",
                moed="Bet",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 2),
                excluded_dates=[],
            ),
            ExamPeriod(
                semester="SPRI",
                moed="Aleph",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 2),
                excluded_dates=[],
            ),
        ]

        systems = ExamScheduleGenerator().generate_exam_systems([course], periods)

        self.assertEqual(len(systems), 4)
        for system in systems:
            self.assertEqual(
                [(schedule.semester, schedule.moed) for schedule in system.period_schedules],
                [("FALL", "Aleph"), ("FALL", "Bet")],
            )


if __name__ == "__main__":
    unittest.main()
