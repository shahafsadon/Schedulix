import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from models import Course, ProgramEnrollment
from gui.programDetailsPresenter import ProgramDetailsPresenter


def course(name, number, enrollments, evaluation_type="Exam", instructor="Dr. Test"):
    """Build a Course from a list of (program, year, semester, status) tuples."""
    return Course(
        name=name,
        course_number=number,
        instructor=instructor,
        programs=[ProgramEnrollment(*enrollment) for enrollment in enrollments],
        evaluation_type=evaluation_type,
    )


class ProgramDetailsPresenterTests(unittest.TestCase):
    """Tests for building the per-program detail view (no GUI involved)."""

    def test_only_includes_courses_of_requested_program(self) -> None:
        courses = [
            course("Physics 1", "83102", [("83101", 1, "FALL", "Obligatory")]),
            course("Other", "83200", [("83108", 1, "FALL", "Obligatory")]),
        ]
        details = ProgramDetailsPresenter(courses).get_details("83101")
        self.assertEqual(details.program_number, "83101")
        self.assertEqual(details.course_count, 1)
        self.assertEqual(details.groups[0].courses[0].name, "Physics 1")

    def test_groups_courses_by_year_then_semester(self) -> None:
        courses = [
            course("Spring Y2", "83300", [("83101", 2, "SPRI", "Elective")]),
            course("Fall Y1", "83100", [("83101", 1, "FALL", "Obligatory")]),
            course("Fall Y2", "83200", [("83101", 2, "FALL", "Obligatory")]),
        ]
        details = ProgramDetailsPresenter(courses).get_details("83101")
        ordered = [(g.year, g.semester) for g in details.groups]
        self.assertEqual(ordered, [(1, "FALL"), (2, "FALL"), (2, "SPRI")])

    def test_exposes_status_and_evaluation_type(self) -> None:
        courses = [
            course(
                "Seminar",
                "83400",
                [("83101", 3, "SPRI", "Elective")],
                evaluation_type="Attendance",
            ),
        ]
        details = ProgramDetailsPresenter(courses).get_details("83101")
        detail = details.groups[0].courses[0]
        self.assertEqual(detail.status, "Elective")
        self.assertEqual(detail.evaluation_type, "Attendance")

    def test_same_course_in_two_slots_appears_in_each(self) -> None:
        courses = [
            course(
                "Shared",
                "83500",
                [
                    ("83101", 1, "FALL", "Obligatory"),
                    ("83101", 2, "SPRI", "Elective"),
                ],
            ),
        ]
        details = ProgramDetailsPresenter(courses).get_details("83101")
        self.assertEqual(details.course_count, 2)
        self.assertEqual(len(details.groups), 2)

    def test_courses_within_group_sorted_by_course_number(self) -> None:
        courses = [
            course("B", "83999", [("83101", 1, "FALL", "Obligatory")]),
            course("A", "83001", [("83101", 1, "FALL", "Obligatory")]),
        ]
        details = ProgramDetailsPresenter(courses).get_details("83101")
        numbers = [c.course_number for c in details.groups[0].courses]
        self.assertEqual(numbers, ["83001", "83999"])

    def test_unknown_program_returns_empty_details(self) -> None:
        courses = [course("Physics 1", "83102", [("83101", 1, "FALL", "Obligatory")])]
        details = ProgramDetailsPresenter(courses).get_details("99999")
        self.assertEqual(details.course_count, 0)
        self.assertEqual(details.groups, [])


if __name__ == "__main__":
    unittest.main()