"""Unit tests for ExportService (SCRUM-127).

These tests verify the service writes one system through OutputWriter, returns
a success outcome with the actual path, and turns OS errors into a friendly
failure outcome. A temporary directory keeps the real data/outputs untouched.
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from models import Course, ProgramEnrollment
from output.exportService import ExportService
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


def make_system() -> ExamSystem:
    """Build a minimal one-exam ExamSystem for export tests."""
    course = Course(
        name="Physics 1",
        course_number="83102",
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )
    return ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=[ScheduledExam(course=course, exam_date=date(2026, 1, 29))],
            )
        ]
    )


class ExportServiceTests(unittest.TestCase):
    """ExportService behavior against a real but isolated file system."""

    def setUp(self) -> None:
        """Provide an isolated temp directory for each test."""
        # Temp dir is removed in tearDown so tests never leak files.
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        """Remove the temporary directory and its files."""
        self._tmp.cleanup()

    def test_writes_file_and_returns_success_outcome(self) -> None:
        """A valid path produces a real file and a success outcome."""
        target = self.tmp_path / "exam_schedules.txt"

        outcome = ExportService().export(make_system(), target)

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.path, target)
        self.assertTrue(target.exists())
        # The file must contain the v1.0 header so its format is verifiable.
        self.assertIn("Schedulix Exam Schedules", target.read_text(encoding="utf-8"))

    def test_creates_missing_directories(self) -> None:
        """An export path with non-existent parents is created on the fly."""
        # OutputWriter is documented to create parent directories.
        nested = self.tmp_path / "deeper" / "still" / "output.txt"

        outcome = ExportService().export(make_system(), nested)

        self.assertTrue(outcome.success)
        self.assertTrue(nested.exists())

    def test_os_error_becomes_failure_outcome(self) -> None:
        """A writer that raises OSError yields a failure outcome, not a crash."""

        class _FakeWriter:
            def write(self, schedules, output_path):
                raise PermissionError("denied")

        outcome = ExportService(output_writer=_FakeWriter()).export(
            make_system(), self.tmp_path / "x.txt"
        )

        self.assertFalse(outcome.success)
        self.assertIn("denied", outcome.error_message)
        self.assertIsNone(outcome.path)

    def test_unexpected_error_becomes_failure_outcome(self) -> None:
        """Any non-OSError is caught and returned as a clean failure."""

        class _ExplodingWriter:
            def write(self, schedules, output_path):
                raise RuntimeError("boom")

        outcome = ExportService(output_writer=_ExplodingWriter()).export(
            make_system(), self.tmp_path / "x.txt"
        )

        self.assertFalse(outcome.success)
        self.assertIn("RuntimeError", outcome.error_message)


if __name__ == "__main__":
    unittest.main()