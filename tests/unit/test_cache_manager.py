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

from application.cache_manager import CacheManager, MAX_PERSISTED_GENERATED_SCHEDULES
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

    def test_reload_invalidates_oversized_generated_schedule_cache(self) -> None:
        """Restart should keep uploaded inputs but discard unsafe derived data."""
        first = CacheManager()
        first.set_courses([_make_course()])
        first.set_generated_schedules(
            [
                _make_exam_system()
                for _index in range(MAX_PERSISTED_GENERATED_SCHEDULES + 1)
            ]
        )

        second = CacheManager()

        self.assertEqual(len(second.get_courses()), 1)
        self.assertEqual(second.get_generated_schedules(), [])
        self.assertEqual(second.get_ranked_schedules(), [])
        self.assertEqual(second.get_result_mode(), "unranked_generated")


class TestCacheManagerIncrementalUpdates(_CacheManagerTestBase):
    """Verify add_* methods append items without replacing existing data."""

    def test_add_courses_extends_existing_list(self) -> None:
        """add_courses appends to existing courses instead of replacing them."""
        cache = CacheManager()
        cache.set_courses([_make_course("Physics 1", "83102")])

        cache.add_courses([_make_course("Calculus 1", "83112")])

        result = cache.get_courses()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Physics 1")
        self.assertEqual(result[1].name, "Calculus 1")

    def test_add_courses_ignores_an_exact_duplicate(self) -> None:
        """Appending the same course twice must keep one course record."""
        cache = CacheManager()
        course = _make_course("Physics 1", "83102")
        cache.set_courses([course])

        cache.add_courses([course])

        self.assertEqual(len(cache.get_courses()), 1)

    def test_add_courses_merges_new_program_enrollment(self) -> None:
        """The same course may be merged when it belongs to another program."""
        cache = CacheManager()
        cache.set_courses([_make_course("Physics 1", "83102")])
        second_program = _make_course("Physics 1", "83102")
        second_program.programs = [
            ProgramEnrollment("83108", 2, "SPRI", "Obligatory")
        ]

        cache.add_courses([second_program])

        saved_course = cache.get_courses()[0]
        self.assertEqual(len(cache.get_courses()), 1)
        self.assertEqual(
            [program.program_number for program in saved_course.programs],
            ["83101", "83108"],
        )

    def test_add_courses_rejects_conflicting_course_details(self) -> None:
        """One course number must not silently describe two different courses."""
        cache = CacheManager()
        cache.set_courses([_make_course("Physics 1", "83102")])

        with self.assertRaisesRegex(ValueError, "conflicting course details"):
            cache.add_courses([_make_course("Different Physics", "83102")])

        self.assertEqual(len(cache.get_courses()), 1)

    def test_reload_repairs_exact_duplicate_courses(self) -> None:
        """A saved cache with duplicate uploads is cleaned on the next start."""
        first = CacheManager()
        course = _make_course("Physics 1", "83102")
        first._state.courses = [course, course]
        first._persist()

        restored = CacheManager()

        self.assertEqual(len(restored.get_courses()), 1)

    def test_add_exam_periods_extends_existing_list(self) -> None:
        """add_exam_periods appends to existing periods instead of replacing."""
        cache = CacheManager()
        cache.set_exam_periods([_make_exam_period("FALL", "Aleph")])

        cache.add_exam_periods([_make_exam_period("SPRI", "Bet")])

        result = cache.get_exam_periods()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].semester, "FALL")
        self.assertEqual(result[1].semester, "SPRI")

    def test_add_selected_programs_extends_existing_list(self) -> None:
        """add_selected_programs appends new programs to existing ones."""
        cache = CacheManager()
        cache.set_selected_programs(["83101"])

        cache.add_selected_programs(["83108"])

        self.assertEqual(cache.get_selected_programs(), ["83101", "83108"])

    def test_add_generated_schedules_extends_existing_list(self) -> None:
        """add_generated_schedules appends to existing schedules."""
        cache = CacheManager()
        cache.set_generated_schedules([_make_exam_system()])

        cache.add_generated_schedules([_make_exam_system()])

        self.assertEqual(len(cache.get_generated_schedules()), 2)

    def test_add_courses_to_empty_cache(self) -> None:
        """add_courses works correctly when the courses list starts empty."""
        cache = CacheManager()

        cache.add_courses([_make_course("New Course", "55555")])

        result = cache.get_courses()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "New Course")

    def test_add_courses_persists_to_pkl(self) -> None:
        """add_courses must create/update the pkl file on disk."""
        cache = CacheManager()
        self.assertFalse(CacheManager._PKL_PATH.exists())

        cache.add_courses([_make_course()])

        self.assertTrue(CacheManager._PKL_PATH.exists())

    def test_add_courses_round_trip(self) -> None:
        """Incrementally added courses survive a full pickle round-trip."""
        first = CacheManager()
        first.set_courses([_make_course("Course A", "11111")])
        first.add_courses([_make_course("Course B", "22222")])

        second = CacheManager()

        result = second.get_courses()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Course A")
        self.assertEqual(result[1].name, "Course B")

    def test_add_selected_programs_deduplicates(self) -> None:
        """Adding a program number that already exists must not create a duplicate."""
        cache = CacheManager()
        cache.set_selected_programs(["83101"])

        cache.add_selected_programs(["83101", "83108"])

        self.assertEqual(cache.get_selected_programs(), ["83101", "83108"])

    def test_add_then_set_replaces_all_added_items(self) -> None:
        """Calling set_courses after add_courses discards all previously added items."""
        cache = CacheManager()
        cache.add_courses([_make_course("Old A", "11111")])
        cache.add_courses([_make_course("Old B", "22222")])

        cache.set_courses([_make_course("Fresh", "99999")])

        result = cache.get_courses()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Fresh")

    def test_set_then_add_appends_to_override(self) -> None:
        """add_courses after set_courses appends to the overridden list."""
        cache = CacheManager()
        cache.set_courses([_make_course("Base", "11111")])

        cache.add_courses([_make_course("Extra", "22222")])

        result = cache.get_courses()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Base")
        self.assertEqual(result[1].name, "Extra")


class TestCacheManagerPerFieldInvalidation(_CacheManagerTestBase):
    """Verify invalidate_* methods clear one field while leaving others intact."""

    def _fill_all_fields(self, cache: CacheManager) -> None:
        """Helper: populate all four fields with one item each."""
        cache.set_courses([_make_course()])
        cache.set_exam_periods([_make_exam_period()])
        cache.set_selected_programs(["83101"])
        cache.set_generated_schedules([_make_exam_system()])

    def test_invalidate_courses_clears_only_courses(self) -> None:
        """invalidate_courses empties courses but leaves other fields intact."""
        cache = CacheManager()
        self._fill_all_fields(cache)

        cache.invalidate_courses()

        self.assertEqual(cache.get_courses(), [])
        self.assertEqual(len(cache.get_exam_periods()), 1)
        self.assertEqual(cache.get_selected_programs(), ["83101"])
        self.assertEqual(len(cache.get_generated_schedules()), 1)

    def test_invalidate_exam_periods_clears_only_exam_periods(self) -> None:
        """invalidate_exam_periods empties periods but leaves other fields intact."""
        cache = CacheManager()
        self._fill_all_fields(cache)

        cache.invalidate_exam_periods()

        self.assertEqual(len(cache.get_courses()), 1)
        self.assertEqual(cache.get_exam_periods(), [])
        self.assertEqual(cache.get_selected_programs(), ["83101"])
        self.assertEqual(len(cache.get_generated_schedules()), 1)

    def test_invalidate_selected_programs_clears_only_programs(self) -> None:
        """invalidate_selected_programs empties programs but leaves other fields."""
        cache = CacheManager()
        self._fill_all_fields(cache)

        cache.invalidate_selected_programs()

        self.assertEqual(len(cache.get_courses()), 1)
        self.assertEqual(len(cache.get_exam_periods()), 1)
        self.assertEqual(cache.get_selected_programs(), [])
        self.assertEqual(len(cache.get_generated_schedules()), 1)

    def test_invalidate_generated_schedules_clears_only_schedules(self) -> None:
        """invalidate_generated_schedules empties schedules but leaves other fields."""
        cache = CacheManager()
        self._fill_all_fields(cache)

        cache.invalidate_generated_schedules()

        self.assertEqual(len(cache.get_courses()), 1)
        self.assertEqual(len(cache.get_exam_periods()), 1)
        self.assertEqual(cache.get_selected_programs(), ["83101"])
        self.assertEqual(cache.get_generated_schedules(), [])

    def test_invalidate_courses_persists_change_to_disk(self) -> None:
        """invalidate_courses must update the pkl file, not delete it."""
        cache = CacheManager()
        self._fill_all_fields(cache)
        self.assertTrue(CacheManager._PKL_PATH.exists())

        cache.invalidate_courses()

        # File must still exist (partial state is persisted, not deleted).
        self.assertTrue(CacheManager._PKL_PATH.exists())

    def test_invalidate_then_reload_sees_empty_field(self) -> None:
        """A new instance created after invalidation sees the cleared field as empty."""
        first = CacheManager()
        self._fill_all_fields(first)
        first.invalidate_courses()

        second = CacheManager()

        self.assertEqual(second.get_courses(), [])

    def test_invalidate_then_reload_keeps_other_fields(self) -> None:
        """A new instance created after invalidation still has the untouched fields."""
        first = CacheManager()
        self._fill_all_fields(first)
        first.invalidate_courses()

        second = CacheManager()

        self.assertEqual(len(second.get_exam_periods()), 1)
        self.assertEqual(second.get_selected_programs(), ["83101"])
        self.assertEqual(len(second.get_generated_schedules()), 1)

    def test_invalidate_all_fields_individually_leaves_empty_pkl(self) -> None:
        """
        Four sequential invalidate_* calls leave the pkl file present but empty.

        This is the key difference from clear(): the file survives (with an
        all-empty payload) instead of being deleted.
        """
        cache = CacheManager()
        self._fill_all_fields(cache)

        cache.invalidate_courses()
        cache.invalidate_exam_periods()
        cache.invalidate_selected_programs()
        cache.invalidate_generated_schedules()

        # File must still exist — unlike clear() which deletes it.
        self.assertTrue(CacheManager._PKL_PATH.exists())

        # All fields must be empty.
        self.assertEqual(cache.get_courses(), [])
        self.assertEqual(cache.get_exam_periods(), [])
        self.assertEqual(cache.get_selected_programs(), [])
        self.assertEqual(cache.get_generated_schedules(), [])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
