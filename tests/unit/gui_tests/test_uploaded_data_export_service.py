"""Unit tests for uploaded-data export support (SCRUM-120)."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from fileReader.baseFileReader import FileReaderType
from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
from fileReader.fileTypeReaders.programReader import ProgramsFileReader
from gui.services.uploadedDataExportService import UploadedDataExportService
from models import Course, ExamPeriod, ProgramEnrollment


def _make_course(
    name: str = "Physics 1",
    number: str = "83102",
) -> Course:
    return Course(
        name=name,
        course_number=number,
        instructor="Prof. Test",
        programs=[
            ProgramEnrollment("83101", 1, "FALL", "Obligatory"),
            ProgramEnrollment("83102", 1, "FALL", "Elective"),
        ],
        evaluation_type="Exam",
    )


def _make_exam_period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        excluded_dates=[date(2026, 1, 3), date(2026, 1, 4)],
    )


class UploadedDataExportServiceTests(unittest.TestCase):
    """UploadedDataExportService writes valid downloadable dataset files."""

    def setUp(self) -> None:
        """Redirect CacheManager persistence so tests never touch real state."""
        self._temp_cache_dir = tempfile.TemporaryDirectory()
        self._tmp_dir = Path(self._temp_cache_dir.name)
        self._original_pkl_path = CacheManager._PKL_PATH
        CacheManager._PKL_PATH = self._tmp_dir / "internal_data.pkl"

    def tearDown(self) -> None:
        """Restore CacheManager persistence after each test."""
        CacheManager._PKL_PATH = self._original_pkl_path
        self._temp_cache_dir.cleanup()

    def test_export_courses_writes_reader_compatible_file(self) -> None:
        """Exported courses can be read back by the existing courses reader."""
        cache = CacheManager()
        cache.set_courses([_make_course(), _make_course("Calculus 1", "83112")])
        export_path = self._tmp_dir / "courses_export.txt"

        result = UploadedDataExportService(cache_manager=cache).export_courses(
            export_path
        )
        exported = CoursesFileReader().read(export_path)

        self.assertTrue(result.success)
        self.assertEqual(result.item_count, 2)
        self.assertEqual(len(exported), 2)
        self.assertEqual(exported[0].course_number, "83102")
        self.assertEqual(exported[1].name, "Calculus 1")

    def test_export_programs_writes_reader_compatible_file(self) -> None:
        """Exported selected programs can be read back by the programs reader."""
        cache = CacheManager()
        cache.set_selected_programs(["83101", "83102", "83108"])
        export_path = self._tmp_dir / "programs_export.txt"

        result = UploadedDataExportService(cache_manager=cache).export_programs(
            export_path
        )
        exported = ProgramsFileReader().read(export_path)

        self.assertTrue(result.success)
        self.assertEqual(result.item_count, 3)
        self.assertEqual(exported, ["83101", "83102", "83108"])

    def test_export_exam_periods_writes_reader_compatible_file(self) -> None:
        """Exported exam periods can be read back by the dates reader."""
        cache = CacheManager()
        cache.set_exam_periods([_make_exam_period()])
        export_path = self._tmp_dir / "periods_export.txt"

        result = UploadedDataExportService(cache_manager=cache).export_exam_periods(
            export_path
        )
        exported = ExamPeriodsFileReader().read(export_path)

        self.assertTrue(result.success)
        self.assertEqual(result.item_count, 1)
        self.assertEqual(exported[0].semester, "FALL")
        self.assertEqual(exported[0].moed, "Aleph")
        self.assertEqual(len(exported[0].excluded_dates), 2)

    def test_empty_dataset_returns_failure_without_creating_file(self) -> None:
        """Exporting a missing dataset fails before writing an empty file."""
        export_path = self._tmp_dir / "missing_courses.txt"

        result = UploadedDataExportService(cache_manager=CacheManager()).export_courses(
            export_path
        )

        self.assertFalse(result.success)
        self.assertIn("No Courses file data", result.message)
        self.assertFalse(export_path.exists())

    def test_export_uses_local_uploaded_data_when_no_cache_is_injected(self) -> None:
        """Standalone export works from UploadedInputData-style local state."""
        from gui.services.uploadService import UploadedInputData

        uploaded_data = UploadedInputData(programs=["83101"])
        export_path = self._tmp_dir / "local_programs.txt"

        result = UploadedDataExportService(uploaded_data=uploaded_data).export_programs(
            export_path
        )

        self.assertTrue(result.success)
        self.assertEqual(ProgramsFileReader().read(export_path), ["83101"])

    def test_write_failure_returns_failure_result(self) -> None:
        """Filesystem write errors are converted into user-facing failures."""
        cache = CacheManager()
        cache.set_courses([_make_course()])

        result = UploadedDataExportService(cache_manager=cache).export_courses(
            self._tmp_dir
        )

        self.assertFalse(result.success)
        self.assertIn("export failed", result.message)

    def test_validation_failure_returns_failure_result(self) -> None:
        """A generated file that cannot validate is reported as a failure."""
        cache = CacheManager()
        cache.set_courses([_make_course()])
        export_path = self._tmp_dir / "bad_validation.txt"
        fake_reader = MagicMock()
        fake_reader.read.return_value = []

        with patch(
            "gui.services.uploadedDataExportService.FileReaderFactory.get_reader",
            return_value=fake_reader,
        ):
            result = UploadedDataExportService(cache_manager=cache).export(
                FileReaderType.COURSES,
                export_path,
            )

        self.assertFalse(result.success)
        self.assertIn("Export validation failed", result.message)


if __name__ == "__main__":
    unittest.main()
