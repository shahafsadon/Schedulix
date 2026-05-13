import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FILE_READER = SRC / "fileReader"

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(FILE_READER))

from models import Course, ProgramEnrollment
from scheduling.courseFilter import CourseFilter


class CourseFilterTests(unittest.TestCase):
    """Tests for selecting only courses that should be scheduled."""

    def test_keeps_only_exam_courses_from_selected_programs(self) -> None:
        """Project and Attendance courses should not be scheduled."""
        courses = [
            Course(
                name="Physics 1",
                course_number="83102",
                instructor="Prof. O. Some",
                programs=[
                    ProgramEnrollment("83101", 1, "FALL", "Obligatory"),
                    ProgramEnrollment("83108", 2, "FALL", "Elective"),
                ],
                evaluation_type="Exam",
            ),
            Course(
                name="Software Project",
                course_number="83533",
                instructor="Dr. Terry Bell",
                programs=[ProgramEnrollment("83101", 3, "SPRI", "Elective")],
                evaluation_type="Project",
            ),
            Course(
                name="Seminar",
                course_number="83999",
                instructor="Dr. A. Speaker",
                programs=[ProgramEnrollment("83101", 4, "SPRI", "Obligatory")],
                evaluation_type="Attendance",
            ),
        ]

        result = CourseFilter().filter_relevant_courses(courses, ["83101"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Physics 1")
        self.assertEqual(result[0].evaluation_type, "Exam")
        self.assertEqual(result[0].programs[0].program_number, "83101")
        self.assertEqual(result[0].programs[0].year, 1)
        self.assertEqual(result[0].programs[0].semester, "FALL")
        self.assertEqual(result[0].programs[0].status, "Obligatory")

    def test_removes_exam_courses_that_do_not_belong_to_selected_programs(self) -> None:
        """An Exam course is irrelevant if none of its programs were selected."""
        courses = [
            Course(
                name="Calculus 1",
                course_number="83112",
                instructor="Dr. Erez Scheiner",
                programs=[ProgramEnrollment("83102", 1, "FALL", "Obligatory")],
                evaluation_type="Exam",
            )
        ]

        result = CourseFilter().filter_relevant_courses(courses, ["83101"])

        self.assertEqual(result, [])

    def test_does_not_change_original_course_programs(self) -> None:
        """Filtering should not remove data from the original Course object."""
        course = Course(
            name="Physics 1",
            course_number="83102",
            instructor="Prof. O. Some",
            programs=[
                ProgramEnrollment("83101", 1, "FALL", "Obligatory"),
                ProgramEnrollment("83108", 2, "FALL", "Elective"),
            ],
            evaluation_type="Exam",
        )

        result = CourseFilter().filter_relevant_courses([course], ["83101"])

        self.assertEqual(len(course.programs), 2)
        self.assertEqual(len(result[0].programs), 1)


if __name__ == "__main__":
    unittest.main()
