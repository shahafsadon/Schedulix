import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from constraint_settings import ThresholdConstraintType
from fileReader.baseFileReader import FileReaderType
from gui.services.uploadService import FileUploadService, UploadMode

EXAMPLES = ROOT / "data" / "examples" / "basic_course_example"
COURSES_PATH = EXAMPLES / "courses.txt"
PROGRAMS_PATH = EXAMPLES / "programs.txt"
PERIODS_PATH = EXAMPLES / "dates.txt"


class FileUploadServiceTests(unittest.TestCase):
    """Tests for the GUI upload service that connects to existing readers."""

    def setUp(self) -> None:
        """Redirect CacheManager persistence so tests never touch real state."""
        self._temp_cache_dir = tempfile.TemporaryDirectory()
        self._original_pkl_path = CacheManager._PKL_PATH
        CacheManager._PKL_PATH = Path(self._temp_cache_dir.name) / "internal_data.pkl"

    def tearDown(self) -> None:
        """Restore CacheManager persistence after each test."""
        CacheManager._PKL_PATH = self._original_pkl_path
        self._temp_cache_dir.cleanup()

    def test_uploads_all_required_example_files(self) -> None:
        service = FileUploadService()

        courses = service.upload_courses(COURSES_PATH)
        programs = service.upload_programs(PROGRAMS_PATH)
        periods = service.upload_exam_periods(PERIODS_PATH)

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

        service.upload_courses(COURSES_PATH)
        self.assertFalse(service.is_ready_for_scheduling())

        service.upload_programs(PROGRAMS_PATH)
        self.assertFalse(service.is_ready_for_scheduling())

        service.upload_exam_periods(PERIODS_PATH)
        self.assertTrue(service.is_ready_for_scheduling())

    def test_replace_upload_synchronizes_courses_to_cache(self) -> None:
        """Replace mode stores parsed courses as the cached source of truth."""
        cache = CacheManager()
        service = FileUploadService(cache_manager=cache)

        result = service.upload_courses(
            COURSES_PATH,
            mode=UploadMode.REPLACE,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.mode, UploadMode.REPLACE)
        self.assertEqual(result.cached_count, 3)
        self.assertEqual(len(cache.get_courses()), 3)
        self.assertEqual(len(service.get_uploaded_data().courses), 3)

    def test_append_upload_extends_cached_courses(self) -> None:
        """Append mode adds newly parsed courses without discarding old ones."""
        cache = CacheManager()
        service = FileUploadService(cache_manager=cache)
        extra_courses_path = self._write_course_file(
            "extra_courses.txt",
            "Linear Algebra",
            "83222",
        )

        service.upload_courses(COURSES_PATH)
        result = service.upload_courses(extra_courses_path, mode=UploadMode.APPEND)

        self.assertTrue(result.success)
        self.assertEqual(result.mode, UploadMode.APPEND)
        self.assertEqual(result.item_count, 1)
        self.assertEqual(result.cached_count, 4)
        self.assertEqual(len(cache.get_courses()), 4)
        self.assertEqual(len(service.get_uploaded_data().courses), 4)

    def test_append_same_courses_file_does_not_duplicate_courses(self) -> None:
        """Repeating one courses upload keeps the cache ready for scheduling."""
        cache = CacheManager()
        service = FileUploadService(cache_manager=cache)
        courses_path = COURSES_PATH

        service.upload_courses(courses_path)
        result = service.upload_courses(courses_path, mode=UploadMode.APPEND)

        self.assertTrue(result.success)
        self.assertEqual(result.cached_count, 3)
        self.assertEqual(len(cache.get_courses()), 3)
        self.assertEqual(len(service.get_uploaded_data().courses), 3)

    def test_append_programs_deduplicates_cached_selection(self) -> None:
        """Appending selected programs keeps each program number only once."""
        cache = CacheManager()
        service = FileUploadService(cache_manager=cache)
        example_programs = PROGRAMS_PATH

        service.upload_programs(example_programs)
        result = service.upload_programs(example_programs, mode=UploadMode.APPEND)

        self.assertTrue(result.success)
        self.assertEqual(result.cached_count, 3)
        self.assertEqual(cache.get_selected_programs(), ["83101", "83102", "83108"])
        self.assertEqual(
            service.get_uploaded_data().programs,
            ["83101", "83102", "83108"],
        )

    def test_successful_input_update_invalidates_generated_schedules(self) -> None:
        """Changing input data clears stale generated schedule results."""
        cache = CacheManager()
        cache.set_generated_schedules(["old schedule"])
        service = FileUploadService(cache_manager=cache)

        service.upload_courses(COURSES_PATH)

        self.assertEqual(cache.get_generated_schedules(), [])

    def test_failed_upload_with_cache_preserves_previous_courses(self) -> None:
        """Reader failures must not replace or append over valid cached data."""
        cache = CacheManager()
        service = FileUploadService(cache_manager=cache)
        service.upload_courses(COURSES_PATH)

        invalid_courses_path = Path(self._temp_cache_dir.name) / "invalid_courses.txt"
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

        result = service.upload_courses(invalid_courses_path, mode=UploadMode.APPEND)

        self.assertFalse(result.success)
        self.assertEqual(result.cached_count, 3)
        self.assertEqual(len(cache.get_courses()), 3)
        self.assertEqual(len(service.get_uploaded_data().courses), 3)

    def test_colocated_settings_file_is_preloaded_after_required_uploads(self) -> None:
        cache = CacheManager()
        service = FileUploadService(cache_manager=cache)
        demo = ROOT / "data" / "examples" / "fallback_compromise_demo"

        service.upload_courses(demo / "courses.txt")
        service.upload_programs(demo / "programs.txt")
        service.upload_exam_periods(demo / "dates.txt")

        mandatory_gap = cache.get_constraint_settings().constraints[
            ThresholdConstraintType.mandatory_gap_days
        ]
        self.assertTrue(mandatory_gap.enabled)
        self.assertEqual(mandatory_gap.k, 10)
        self.assertTrue(cache.get_ranking_settings().priority_list)

    def _write_course_file(self, filename: str, name: str, number: str) -> Path:
        """Create a valid one-course input file inside this test's temp folder."""
        path = Path(self._temp_cache_dir.name) / filename
        path.write_text(
            f"""$$$$
{name}
{number}
Dr. Test
83101,1,FALL,Obligatory
Exam
""",
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
