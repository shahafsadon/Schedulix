"""
test_cache_manager.py
~~~~~~~~~~~~~~~~~~~~~
Isolated unit tests for the CacheManager state manager.

Each test redirects ``CacheManager._PKL_PATH`` to a unique temporary file
inside pytest's ``tmp_path`` fixture so that no real ``internal_data.pkl``
is written to the project tree during the test run. The class attribute is
restored after every test to prevent cross-test contamination.

Test coverage
-------------
* Initial empty state
* set/get for every field (RAM only)
* Pickle file is created on first mutating call
* Full round-trip: second instance reloads all fields from disk
* ``clear()`` resets RAM to empty lists
* ``clear()`` deletes the pickle file from disk
* No crash when the pickle file is absent on startup
"""

import sys
import unittest
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup – mirrors the pattern used by existing unit tests in this project
# ---------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[1]   # tests/
_SRC = _TESTS_ROOT.parent / "src"                   # src/

sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Imports from the project under test
# ---------------------------------------------------------------------------

from application.cache_manager import CacheManager
from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.examConflictDetector import ScheduledExam


# ---------------------------------------------------------------------------
# Shared test-data factories
# ---------------------------------------------------------------------------

def _make_course(name: str = "Physics 1", number: str = "83102") -> Course:
    return Course(
        name=name,
        course_number=number,
        instructor="Prof. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def _make_exam_period(semester: str = "FALL", moed: str = "Aleph") -> ExamPeriod:
    return ExamPeriod(
        semester=semester,
        moed=moed,
        start_date=date(2025, 1, 20),
        end_date=date(2025, 2, 10),
        excluded_dates=[],
    )


def _make_exam_system() -> ExamSystem:
    course = _make_course()
    period = _make_exam_period()
    scheduled_exam = ScheduledExam(course=course, exam_date=date(2025, 1, 22))
    schedule = ExamSchedule(
        semester=period.semester,
        moed=period.moed,
        scheduled_exams=[scheduled_exam],
    )
    return ExamSystem(period_schedules=[schedule])


# ---------------------------------------------------------------------------
# Base class – handles _PKL_PATH redirection and cleanup
# ---------------------------------------------------------------------------

class _CacheManagerTestBase(unittest.TestCase):
    """
    Sets up a temporary pickle path before each test and restores the
    original class attribute afterwards. Tests never write to the real
    ``internal_data.pkl`` inside the project tree.
    """

    # Populated by setUp; each test method gets its own directory.
    _tmp_dir: Path
    _original_pkl_path: Path

    def setUp(self) -> None:
        # Create a unique temporary directory for this test.
        import tempfile
        self._tmp_dir = Path(tempfile.mkdtemp())
        self._original_pkl_path = CacheManager._PKL_PATH
        # Redirect pickle I/O to the temp dir.
        CacheManager._PKL_PATH = self._tmp_dir / "internal_data.pkl"

    def tearDown(self) -> None:
        # Restore the original path so other tests are unaffected.
        CacheManager._PKL_PATH = self._original_pkl_path
        # Remove any leftover file (belt-and-suspenders cleanup).
        tmp_pkl = self._tmp_dir / "internal_data.pkl"
        if tmp_pkl.exists():
            tmp_pkl.unlink()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestCacheManagerInitialState(_CacheManagerTestBase):
    """Verify that a fresh instance starts with completely empty state."""

    def test_initial_courses_are_empty(self) -> None:
        """get_courses() on a new manager returns an empty list."""
        cache = CacheManager()
        self.assertEqual(cache.get_courses(), [])

    def test_initial_exam_periods_are_empty(self) -> None:
        """get_exam_periods() on a new manager returns an empty list."""
        cache = CacheManager()
        self.assertEqual(cache.get_exam_periods(), [])

    def test_initial_selected_programs_are_empty(self) -> None:
        """get_selected_programs() on a new manager returns an empty list."""
        cache = CacheManager()
        self.assertEqual(cache.get_selected_programs(), [])

    def test_initial_generated_schedules_are_empty(self) -> None:
        """get_generated_schedules() on a new manager returns an empty list."""
        cache = CacheManager()
        self.assertEqual(cache.get_generated_schedules(), [])


class TestCacheManagerRamStorage(_CacheManagerTestBase):
    """Verify that setters store data and getters retrieve it from RAM."""

    def test_set_and_get_courses(self) -> None:
        """Courses stored via set_courses are returned by get_courses."""
        cache = CacheManager()
        courses = [_make_course("Physics 1", "83102"), _make_course("Calculus 1", "83112")]

        cache.set_courses(courses)

        result = cache.get_courses()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Physics 1")
        self.assertEqual(result[1].name, "Calculus 1")

    def test_set_and_get_exam_periods(self) -> None:
        """Exam periods stored via set_exam_periods are returned correctly."""
        cache = CacheManager()
        periods = [_make_exam_period("FALL", "Aleph"), _make_exam_period("SPRI", "Bet")]

        cache.set_exam_periods(periods)

        result = cache.get_exam_periods()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].semester, "FALL")
        self.assertEqual(result[1].moed, "Bet")

    def test_set_and_get_selected_programs(self) -> None:
        """Program numbers stored via set_selected_programs are returned."""
        cache = CacheManager()
        programs = ["83101", "83108"]

        cache.set_selected_programs(programs)

        result = cache.get_selected_programs()
        self.assertEqual(result, ["83101", "83108"])

    def test_set_and_get_generated_schedules(self) -> None:
        """Schedules stored via set_generated_schedules are returned."""
        cache = CacheManager()
        systems = [_make_exam_system()]

        cache.set_generated_schedules(systems)

        result = cache.get_generated_schedules()
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].period_schedules), 1)

    def test_replacing_courses_overwrites_previous_value(self) -> None:
        """Calling set_courses a second time replaces the previous list."""
        cache = CacheManager()
        cache.set_courses([_make_course("Old Course", "00001")])
        cache.set_courses([_make_course("New Course", "99999")])

        result = cache.get_courses()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "New Course")


class TestCacheManagerPicklePersistence(_CacheManagerTestBase):
    """Verify that mutating operations write the pickle file to disk."""

    def test_set_courses_creates_pkl_file(self) -> None:
        """Calling set_courses must create the internal_data.pkl file."""
        cache = CacheManager()
        self.assertFalse(CacheManager._PKL_PATH.exists())

        cache.set_courses([_make_course()])

        self.assertTrue(CacheManager._PKL_PATH.exists())

    def test_set_exam_periods_creates_pkl_file(self) -> None:
        """Calling set_exam_periods must create the internal_data.pkl file."""
        cache = CacheManager()

        cache.set_exam_periods([_make_exam_period()])

        self.assertTrue(CacheManager._PKL_PATH.exists())

    def test_set_selected_programs_creates_pkl_file(self) -> None:
        """Calling set_selected_programs must create the internal_data.pkl file."""
        cache = CacheManager()

        cache.set_selected_programs(["83101"])

        self.assertTrue(CacheManager._PKL_PATH.exists())

    def test_set_generated_schedules_creates_pkl_file(self) -> None:
        """Calling set_generated_schedules must create the internal_data.pkl file."""
        cache = CacheManager()

        cache.set_generated_schedules([_make_exam_system()])

        self.assertTrue(CacheManager._PKL_PATH.exists())


class TestCacheManagerDeserialization(_CacheManagerTestBase):
    """Verify that a second CacheManager instance restores state from disk."""

    def test_reload_restores_courses(self) -> None:
        """A second instance reloads courses persisted by the first instance."""
        first = CacheManager()
        first.set_courses([_make_course("Restored Course", "11111")])

        second = CacheManager()

        result = second.get_courses()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Restored Course")
        self.assertEqual(result[0].course_number, "11111")

    def test_reload_restores_all_fields(self) -> None:
        """All four state fields survive a full pickle round-trip."""
        first = CacheManager()
        first.set_courses([_make_course()])
        first.set_exam_periods([_make_exam_period()])
        first.set_selected_programs(["83101", "83108"])
        first.set_generated_schedules([_make_exam_system()])

        second = CacheManager()

        self.assertEqual(len(second.get_courses()), 1)
        self.assertEqual(len(second.get_exam_periods()), 1)
        self.assertEqual(second.get_selected_programs(), ["83101", "83108"])
        self.assertEqual(len(second.get_generated_schedules()), 1)

    def test_no_crash_when_pkl_file_absent(self) -> None:
        """__init__ must not raise when no pickle file exists yet."""
        self.assertFalse(CacheManager._PKL_PATH.exists())
        try:
            cache = CacheManager()
        except Exception as exc:  # pragma: no cover
            self.fail(f"CacheManager() raised an exception with no pkl file: {exc}")
        self.assertEqual(cache.get_courses(), [])


class TestCacheManagerClear(_CacheManagerTestBase):
    """Verify the clear() lifecycle method behaves correctly."""

    def test_clear_resets_all_ram_fields_to_empty(self) -> None:
        """After clear(), every getter returns an empty list."""
        cache = CacheManager()
        cache.set_courses([_make_course()])
        cache.set_exam_periods([_make_exam_period()])
        cache.set_selected_programs(["83101"])
        cache.set_generated_schedules([_make_exam_system()])

        cache.clear()

        self.assertEqual(cache.get_courses(), [])
        self.assertEqual(cache.get_exam_periods(), [])
        self.assertEqual(cache.get_selected_programs(), [])
        self.assertEqual(cache.get_generated_schedules(), [])

    def test_clear_deletes_pkl_file(self) -> None:
        """After clear(), the internal_data.pkl file no longer exists."""
        cache = CacheManager()
        cache.set_courses([_make_course()])  # ensures the file is created
        self.assertTrue(CacheManager._PKL_PATH.exists())

        cache.clear()

        self.assertFalse(CacheManager._PKL_PATH.exists())

    def test_clear_when_no_file_does_not_raise(self) -> None:
        """clear() must not raise if the pickle file was never created."""
        cache = CacheManager()
        self.assertFalse(CacheManager._PKL_PATH.exists())
        try:
            cache.clear()
        except Exception as exc:  # pragma: no cover
            self.fail(f"clear() raised an exception with no pkl file: {exc}")

    def test_new_instance_after_clear_starts_empty(self) -> None:
        """A new CacheManager created after clear() finds no persisted data."""
        first = CacheManager()
        first.set_courses([_make_course()])
        first.clear()

        second = CacheManager()

        self.assertEqual(second.get_courses(), [])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
