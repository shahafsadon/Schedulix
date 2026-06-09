"""Unit tests for uploaded-data visualization (SCRUM-119)."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from gui.services.uploadService import UploadedInputData
from gui.presenters.uploadedDataPresenter import UploadedDataPresenter
from models import Course, ExamPeriod, ProgramEnrollment


def _make_course(
    name: str = "Physics 1",
    number: str = "83102",
    evaluation_type: str = "Exam",
) -> Course:
    return Course(
        name=name,
        course_number=number,
        instructor="Prof. Test",
        programs=[
            ProgramEnrollment("83101", 1, "FALL", "Obligatory"),
            ProgramEnrollment("83102", 1, "FALL", "Elective"),
        ],
        evaluation_type=evaluation_type,
    )


def _make_exam_period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        excluded_dates=[date(2026, 1, 3)],
    )


class UploadedDataPresenterTests(unittest.TestCase):
    """UploadedDataPresenter builds display-ready parsed-data snapshots."""

    def setUp(self) -> None:
        """Redirect CacheManager persistence so tests never touch real state."""
        self._temp_cache_dir = tempfile.TemporaryDirectory()
        self._original_pkl_path = CacheManager._PKL_PATH
        CacheManager._PKL_PATH = Path(self._temp_cache_dir.name) / "internal_data.pkl"

    def tearDown(self) -> None:
        """Restore CacheManager persistence after each test."""
        CacheManager._PKL_PATH = self._original_pkl_path
        self._temp_cache_dir.cleanup()

    def test_empty_snapshot_reports_no_loaded_data(self) -> None:
        """A presenter with no data returns empty rows and incomplete metadata."""
        snapshot = UploadedDataPresenter(uploaded_data=UploadedInputData()).refresh()

        self.assertEqual(snapshot.courses, [])
        self.assertEqual(snapshot.programs, [])
        self.assertEqual(snapshot.exam_periods, [])
        self.assertEqual(snapshot.metadata.course_count, 0)
        self.assertFalse(snapshot.metadata.is_complete)

    def test_snapshot_reads_courses_programs_and_periods_from_cache(self) -> None:
        """Cache-backed presenter reads the same state later screens consume."""
        cache = CacheManager()
        cache.set_courses([_make_course()])
        cache.set_selected_programs(["83101", "83102"])
        cache.set_exam_periods([_make_exam_period()])

        snapshot = UploadedDataPresenter(cache_manager=cache).refresh()

        self.assertEqual(len(snapshot.courses), 1)
        self.assertEqual(snapshot.programs, ["83101", "83102"])
        self.assertEqual(len(snapshot.exam_periods), 1)
        self.assertTrue(snapshot.metadata.is_complete)

    def test_course_preview_contains_parsed_course_metadata(self) -> None:
        """Course rows expose number, name, instructor, evaluation and programs."""
        data = UploadedInputData(
            courses=[_make_course()],
            programs=[],
            exam_periods=[],
        )

        course = UploadedDataPresenter(uploaded_data=data).refresh().courses[0]

        self.assertEqual(course.course_number, "83102")
        self.assertEqual(course.name, "Physics 1")
        self.assertEqual(course.instructor, "Prof. Test")
        self.assertEqual(course.evaluation_type, "Exam")
        self.assertEqual(course.enrollment_count, 2)
        self.assertEqual(course.program_numbers, ["83101", "83102"])

    def test_exam_period_preview_formats_dates_and_excluded_count(self) -> None:
        """Exam-period rows expose formatted dates, duration and exclusions."""
        data = UploadedInputData(
            courses=[],
            programs=[],
            exam_periods=[_make_exam_period()],
        )

        exam_period = UploadedDataPresenter(uploaded_data=data).refresh().exam_periods[0]

        self.assertEqual(exam_period.semester, "FALL")
        self.assertEqual(exam_period.moed, "Aleph")
        self.assertEqual(exam_period.start_date, "01-01-2026")
        self.assertEqual(exam_period.end_date, "05-01-2026")
        self.assertEqual(exam_period.day_count, 5)
        self.assertEqual(exam_period.excluded_count, 1)

    def test_metadata_counts_evaluation_types_and_enrollments(self) -> None:
        """Metadata summarizes parsed counts needed by the preview."""
        data = UploadedInputData(
            courses=[
                _make_course(evaluation_type="Exam"),
                _make_course("Studio", "83130", "Project"),
            ],
            programs=["83101"],
            exam_periods=[_make_exam_period()],
        )

        metadata = UploadedDataPresenter(uploaded_data=data).refresh().metadata

        self.assertEqual(metadata.course_count, 2)
        self.assertEqual(metadata.program_count, 1)
        self.assertEqual(metadata.exam_period_count, 1)
        self.assertEqual(metadata.exam_course_count, 1)
        self.assertEqual(metadata.total_enrollment_count, 4)
        self.assertEqual(metadata.total_excluded_date_count, 1)
        self.assertEqual(metadata.evaluation_counts, {"Exam": 1, "Project": 1})

    def test_refresh_reflects_later_cache_updates(self) -> None:
        """Calling refresh again picks up data appended after construction."""
        cache = CacheManager()
        cache.set_courses([_make_course("Physics 1", "83102")])
        presenter = UploadedDataPresenter(cache_manager=cache)

        first = presenter.refresh()
        cache.add_courses([_make_course("Calculus 1", "83112")])
        second = presenter.refresh()

        self.assertEqual(first.metadata.course_count, 1)
        self.assertEqual(second.metadata.course_count, 2)
        self.assertEqual(second.courses[1].name, "Calculus 1")


if __name__ == "__main__":
    unittest.main()
