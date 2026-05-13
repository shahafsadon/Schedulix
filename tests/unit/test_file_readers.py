import sys
import unittest
from datetime import date
from pathlib import Path

# Add src to the import path for running tests from the project root.
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from fileReader.fileTypeReaders.programReader import ProgramsFileReader
from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader


class ProgramsFileReaderTests(unittest.TestCase):
    def test_reads_selected_programs(self) -> None:
        # Checks that a valid programs file is split into clean program numbers.
        result = ProgramsFileReader().parse("83101, 83102, 83108")

        self.assertEqual(result, ["83101", "83102", "83108"])

    def test_rejects_more_than_five_programs(self) -> None:
        # Version 1.0 supports up to five selected programs.
        with self.assertRaises(ValueError):
            ProgramsFileReader().parse("83101,83102,83103,83104,83105,83106")


class CoursesFileReaderTests(unittest.TestCase):
    def test_reads_valid_courses_file(self) -> None:
        # Includes one Exam course and one Project course to verify full parsing.
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
        self.assertEqual(courses[0].instructor, "Prof. O. Some")
        self.assertEqual(courses[0].evaluation_type, "Exam")
        self.assertEqual(len(courses[0].programs), 2)
        self.assertEqual(courses[0].programs[0].program_number, "83101")
        self.assertEqual(courses[0].programs[0].year, 1)

    def test_rejects_invalid_evaluation_type(self) -> None:
        # Homework is not a valid evaluation type in the input specification.
        content = """$$$$
Bad Course
83199
Dr. Test
83101,1,FALL,Obligatory
Homework
"""

        with self.assertRaises(ValueError):
            CoursesFileReader().parse(content)


class ExamPeriodsFileReaderTests(unittest.TestCase):
    def test_reads_valid_exam_period(self) -> None:
        # Checks regular excluded dates and excluded date ranges.
        content = """$$$$
FALL, Aleph
29-01-2026, 11-03-2026
- 31-01-2026 Shabat
- 02-03-2026, 04-03-2026 Purim
"""

        periods = ExamPeriodsFileReader().parse(content)

        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].semester, "FALL")
        self.assertEqual(periods[0].moed, "Aleph")
        self.assertEqual(periods[0].start_date, date(2026, 1, 29))
        self.assertEqual(periods[0].end_date, date(2026, 3, 11))
        self.assertIn(date(2026, 3, 3), periods[0].excluded_dates)


if __name__ == "__main__":
    unittest.main()