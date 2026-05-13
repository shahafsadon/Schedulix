import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FILE_READER = SRC / "fileReader"

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(FILE_READER))

from models import Course, ProgramEnrollment
from scheduling.examConflictDetector import (
    ExamConflictDetector,
    ScheduledExam,
)


def make_course(
    name: str,
    course_number: str,
    program_number: str,
    year: int,
    status: str,
) -> Course:
    """Create a small Course object for conflict detector tests."""
    return Course(
        name=name,
        course_number=course_number,
        instructor="Test Instructor",
        programs=[ProgramEnrollment(program_number, year, "FALL", status)],
        evaluation_type="Exam",
    )


class ExamConflictDetectorTests(unittest.TestCase):
    """Tests for version 1.0 critical conflict rules."""

    def test_detects_same_date_same_program_same_year_conflict(self) -> None:
        """Two non-elective exams in the same program year cannot share a date."""
        first_exam = ScheduledExam(
            course=make_course("Physics 1", "83102", "83101", 1, "Obligatory"),
            exam_date=date(2026, 1, 29),
        )
        second_exam = ScheduledExam(
            course=make_course("Calculus 1", "83112", "83101", 1, "Obligatory"),
            exam_date=date(2026, 1, 29),
        )

        conflicts = ExamConflictDetector().find_conflicts([first_exam, second_exam])

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].program_number, "83101")
        self.assertEqual(conflicts[0].year, 1)

    def test_allows_same_date_when_both_courses_are_elective(self) -> None:
        """Two elective courses may share a date by the version 1.0 rule."""
        first_exam = ScheduledExam(
            course=make_course("Elective A", "83120", "83101", 2, "Elective"),
            exam_date=date(2026, 2, 1),
        )
        second_exam = ScheduledExam(
            course=make_course("Elective B", "83121", "83101", 2, "Elective"),
            exam_date=date(2026, 2, 1),
        )

        self.assertTrue(
            ExamConflictDetector().is_valid_schedule([first_exam, second_exam])
        )

    def test_allows_same_date_for_different_programs_or_years(self) -> None:
        """Same-date exams only conflict when program number and year both match."""
        first_exam = ScheduledExam(
            course=make_course("Physics 1", "83102", "83101", 1, "Obligatory"),
            exam_date=date(2026, 1, 29),
        )
        different_program_exam = ScheduledExam(
            course=make_course("Calculus 1", "83112", "83108", 1, "Obligatory"),
            exam_date=date(2026, 1, 29),
        )
        different_year_exam = ScheduledExam(
            course=make_course("Algebra 2", "83113", "83101", 2, "Obligatory"),
            exam_date=date(2026, 1, 29),
        )

        detector = ExamConflictDetector()

        self.assertTrue(
            detector.is_valid_schedule([first_exam, different_program_exam])
        )
        self.assertTrue(detector.is_valid_schedule([first_exam, different_year_exam]))

    def test_allows_same_program_and_year_on_different_dates(self) -> None:
        """Version 1.0 compares dates, so different dates are not conflicts."""
        first_exam = ScheduledExam(
            course=make_course("Physics 1", "83102", "83101", 1, "Obligatory"),
            exam_date=date(2026, 1, 29),
        )
        second_exam = ScheduledExam(
            course=make_course("Calculus 1", "83112", "83101", 1, "Obligatory"),
            exam_date=date(2026, 1, 30),
        )

        self.assertFalse(
            ExamConflictDetector().has_conflicts([first_exam, second_exam])
        )


if __name__ == "__main__":
    unittest.main()
