"""Unit tests for SchedulingService (SCRUM-125).

These tests verify that the service reads from the cache, runs the Version 1.0
filtering and generation, stores results back, and validates required inputs.
A temporary pickle path keeps the real cache file untouched.
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.schedulingService import SchedulingService


def exam_course(name, number, program, semester="FALL", status="Obligatory"):
    """Build a single-enrollment Exam course for service tests."""
    return Course(
        name=name,
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment(program, 1, semester, status)],
        evaluation_type="Exam",
    )


def fall_period():
    """A small FALL Aleph period with two usable dates."""
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        excluded_dates=[],
    )


class SchedulingServiceTests(unittest.TestCase):
    """Service behavior against a temporary, isolated cache."""

    def setUp(self) -> None:
        """Point the cache at a temp file and start from a clean state."""
        # Redirect cache persistence to a temp file so tests never touch the
        # real internal_data.pkl, and start from a guaranteed clean state.
        # The original path is saved so tearDown can restore it, otherwise a
        # later CacheManager() (in another test) would point at a deleted dir.
        self._original_pkl_path = CacheManager._PKL_PATH
        self._tmp = tempfile.TemporaryDirectory()
        CacheManager._PKL_PATH = Path(self._tmp.name) / "test_cache.pkl"
        self.cache = CacheManager()
        self.cache.clear()

    def tearDown(self) -> None:
        """Restore the original cache path and remove the temp directory."""
        # Restore first so the class-level path is valid for any later test,
        # then delete the temporary directory and its cache file.
        CacheManager._PKL_PATH = self._original_pkl_path
        self._tmp.cleanup()

    def test_generates_and_stores_schedules(self) -> None:
        """A complete cache yields schedules that are stored back in the cache."""
        self.cache.set_courses([exam_course("Physics 1", "83102", "83101")])
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

        outcome = SchedulingService().run(self.cache)

        self.assertEqual(outcome.relevant_course_count, 1)
        self.assertGreater(outcome.schedule_count, 0)
        # The schedules must also be persisted into the cache.
        self.assertEqual(
            self.cache.get_generated_schedules(),
            outcome.schedules,
        )
        self.assertEqual(
            self.cache.get_ranked_schedules(),
            outcome.ranked_schedules,
        )
        self.assertEqual(
            len(outcome.ranked_schedules),
            outcome.schedule_count,
        )

    def test_filters_out_non_selected_programs(self) -> None:
        """Courses outside the selected programs are not scheduled."""
        self.cache.set_courses(
            [
                exam_course("In", "83102", "83101"),
                exam_course("Out", "83200", "83108"),
            ]
        )
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

        outcome = SchedulingService().run(self.cache)
        self.assertEqual(outcome.relevant_course_count, 1)

    def test_courses_but_none_in_selected_programs_yields_zero(self) -> None:
        """Courses exist, but none belong to the selected programs.

        This is distinct from "no courses loaded": the run is valid, simply
        producing zero relevant courses and zero schedules.
        """
        self.cache.set_courses([exam_course("Out", "83200", "83108")])
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

        outcome = SchedulingService().run(self.cache)
        self.assertEqual(outcome.relevant_course_count, 0)
        self.assertEqual(outcome.schedule_count, 0)
        self.assertEqual(self.cache.get_generated_schedules(), [])

    def test_missing_courses_raises(self) -> None:
        """Running with no courses is a clear ValueError."""
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])
        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)

    def test_missing_periods_raises(self) -> None:
        """Running with no exam periods is a clear ValueError."""
        self.cache.set_courses([exam_course("Physics 1", "83102", "83101")])
        self.cache.set_selected_programs(["83101"])
        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)

    def test_missing_programs_raises(self) -> None:
        """Running with no selected programs is a clear ValueError."""
        self.cache.set_courses([exam_course("Physics 1", "83102", "83101")])
        self.cache.set_exam_periods([fall_period()])
        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)


if __name__ == "__main__":
    unittest.main()
