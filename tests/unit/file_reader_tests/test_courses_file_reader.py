import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from fileReader.fileTypeReaders.coursesReader import CoursesFileReader


class CoursesFileReaderTests(unittest.TestCase):
    """Unit tests for courses file parsing."""

    def test_reads_valid_courses_file(self) -> None:
        """A valid courses file should create Course objects correctly."""
        content = """$$$$
Physics 1
83102
Prof. O. Some
83101,1,FALL,Obligatory
83102,1,FALL,Obligatory
Exam
$$$$
Software Project
83533
Dr. Terry Bell
83108,2,SPRI,Obligatory
Project
"""

        courses = CoursesFileReader().parse(content)

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0].name, "Physics 1")
        self.assertEqual(courses[0].course_number, "83102")
        self.assertEqual(courses[0].evaluation_type, "Exam")

    def test_rejects_invalid_evaluation_type(self) -> None:
        """Invalid evaluation types should raise ValueError."""
        content = """$$$$
Bad Course
83199
Dr. Test
83101,1,FALL,Obligatory
Homework
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)

    def test_rejects_invalid_program_number(self) -> None:
        """Program numbers must contain exactly five digits."""
        content = """$$$$
Bad Course
83199
Dr. Test
83A01,1,FALL,Obligatory
Exam
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)

    def test_rejects_invalid_year(self) -> None:
        """Academic year must be between 1 and 4."""
        content = """$$$$
Bad Course
83199
Dr. Test
83101,7,FALL,Obligatory
Exam
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)

    def test_rejects_invalid_semester(self) -> None:
        """Semester must be FALL, SPRI, or SUMM."""
        content = """$$$$
Bad Course
83199
Dr. Test
83101,1,WINTER,Obligatory
Exam
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)

    def test_rejects_invalid_status(self) -> None:
        """Status must be Obligatory or Elective."""
        content = """$$$$
Bad Course
83199
Dr. Test
83101,1,FALL,Mandatory
Exam
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)

    def test_rejects_malformed_enrollment_line(self) -> None:
        """Enrollment lines must contain exactly four fields."""
        content = """$$$$
Bad Course
83199
Dr. Test
83101,1,FALL
Exam
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)


if __name__ == "__main__":
    unittest.main()