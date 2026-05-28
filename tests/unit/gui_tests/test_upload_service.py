import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from fileReader.baseFileReader import FileReaderType
from gui.uploadService import FileUploadService


class FileUploadServiceTests(unittest.TestCase):
    """Tests for the GUI upload service that connects to existing readers."""

    def test_uploads_all_required_example_files(self) -> None:
        service = FileUploadService()

        courses = service.upload_courses(ROOT / "data" / "examples" / "CourseExample.txt")
        programs = service.upload_programs(
            ROOT / "data" / "examples" / "ProgramsExample.txt"
        )
        periods = service.upload_exam_periods(
            ROOT / "data" / "examples" / "DatesExample.txt"
        )

        self.assertTrue(courses.success)
        self.assertTrue(programs.success)
        self.assertTrue(periods.success)
        self.assertEqual(courses.item_count, 3)
        self.assertEqual(programs.item_count, 3)
        self.assertEqual(periods.item_count, 3)
        self.assertTrue(service.is_ready_for_scheduling())

    def test_invalid_file_returns_failure_feedback_without_storing_data(self) -> None:
        service = FileUploadService()

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_courses_path = Path(temp_dir) / "invalid_courses.txt"
            invalid_courses_path.write_text(
                """$$$$
Bad Course
8319A
Dr. Test
83101,1,FALL,Obligatory
Exam
""",
                encoding="utf-8",
            )

            result = service.upload_courses(invalid_courses_path)

        self.assertFalse(result.success)
        self.assertIn("upload failed", result.message)
        self.assertIsNone(service.get_uploaded_data().courses)
        self.assertFalse(service.is_ready_for_scheduling())

    def test_missing_file_returns_failure_feedback(self) -> None:
        service = FileUploadService()

        result = service.upload(FileReaderType.PROGRAMS, "missing_programs.txt")

        self.assertFalse(result.success)
        self.assertIn("File not found", result.message)
        self.assertEqual(result.item_count, 0)

    def test_ready_only_after_courses_programs_and_periods_are_loaded(self) -> None:
        service = FileUploadService()

        service.upload_courses(ROOT / "data" / "examples" / "CourseExample.txt")
        self.assertFalse(service.is_ready_for_scheduling())

        service.upload_programs(ROOT / "data" / "examples" / "ProgramsExample.txt")
        self.assertFalse(service.is_ready_for_scheduling())

        service.upload_exam_periods(ROOT / "data" / "examples" / "DatesExample.txt")
        self.assertTrue(service.is_ready_for_scheduling())


if __name__ == "__main__":
    unittest.main()
