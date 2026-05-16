import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from models import Course, ProgramEnrollment
from output.outputWriter import OutputWriter
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


def make_exam(course_name: str, course_number: str, exam_date: date) -> ScheduledExam:
    """Create a scheduled exam for output writer tests."""
    course = Course(
        name=course_name,
        course_number=course_number,
        instructor="Test Instructor",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )
    return ScheduledExam(course=course, exam_date=exam_date)


class OutputWriterTests(unittest.TestCase):
    """Tests for writing readable schedule output files."""

    def test_formats_schedule_with_semester_moed_and_sorted_exams(self) -> None:
        """The text should follow the required readable output structure."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Calculus 1", "83112", date(2026, 2, 1)),
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
                ExamSchedule(
                    semester="FALL",
                    moed="Bet",
                    scheduled_exams=[
                        make_exam("Calculus 1", "83112", date(2026, 4, 10)),
                    ],
                ),
            ],
        )

        result = OutputWriter().format_schedules([schedule])

        self.assertIn("Schedulix Exam Schedules", result)
        self.assertIn("Schedule 1", result)
        self.assertIn("Semester: FALL", result)
        self.assertIn("Moed: Aleph", result)
        self.assertIn("Moed: Bet", result)
        self.assertLess(
            result.index("29-01-2026 | Physics 1 | Test Instructor"),
            result.index("01-02-2026 | Calculus 1 | Test Instructor"),
        )

    def test_writes_output_file_to_given_path(self) -> None:
        """The writer should create the output file and its directory."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="SPRI",
                    moed="Bet",
                    scheduled_exams=[
                        make_exam("Algorithms 1", "83120", date(2026, 7, 3)),
                    ],
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "data" / "outputs" / "exam_schedules.txt"

            created_path = OutputWriter().write([schedule], output_path)

            self.assertEqual(created_path, output_path)
            self.assertTrue(output_path.exists())
            self.assertIn("Semester: SPRI", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
