"""
test_cache_manager_v3.py
~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the v3 CacheManager extensions (SCRUM-144).

Covers:
* Initial default state for the two new settings fields.
* set/get round-trips for constraint_settings and ranking_settings.
* Smart invalidation:
    - set_constraint_settings wipes generated_schedules AND ranked_schedules.
    - set_ranking_settings wipes ONLY ranked_schedules.
* Full pickle round-trips for the new fields.
* v2 backward compatibility: an old sentinel pickle loads without crashing and
  provides correct default values for the two new fields.
* v2 → v3 sentinel upgrade: after any write the file carries the new sentinel.
* Corrupted / unknown pickle falls back to a clean state.
* clear() resets new settings fields to their defaults.

Each test redirects ``CacheManager._PKL_PATH`` to a unique temporary file so
that no real ``internal_data.pkl`` is written to the project tree.
"""

from __future__ import annotations

import pickle
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — mirrors the pattern used by the existing test suite.
# ---------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[1]   # tests/
_SRC = _TESTS_ROOT.parent / "src"                   # src/
sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------

from application.cache_manager import (
    CacheManager,
    _CacheState,
    _SENTINEL,
    _SENTINEL_V2,
)
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ExamPeriod, ProgramEnrollment
from ranking_settings import (
    RankingCriterion,
    RankingPreference,
    RankingSettings,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


# ---------------------------------------------------------------------------
# Shared test-data factories  (identical to the existing suite's helpers)
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


def _make_constraint_settings(
    *,
    gap_k: int = 3,
) -> SchedulingConstraintSettings:
    """Return a simple constraint settings with mandatory_gap_days enabled."""
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_gap_days] = (
        ThresholdConstraintSetting(enabled=True, k=gap_k)
    )
    return settings


def _make_ranking_settings() -> RankingSettings:
    """Return a ranking settings with one criterion."""
    return RankingSettings(
        priority_list=[
            RankingPreference(criterion=RankingCriterion.min_mandatory_gap)
        ]
    )


# ---------------------------------------------------------------------------
# Base class — redirects _PKL_PATH to a temporary file per test.
# ---------------------------------------------------------------------------

class _CacheManagerTestBase(unittest.TestCase):
    """Sets up a temporary pickle path before each test."""

    _tmp_dir: Path
    _original_pkl_path: Path

    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp())
        self._original_pkl_path = CacheManager._PKL_PATH
        CacheManager._PKL_PATH = self._tmp_dir / "internal_data.pkl"

    def tearDown(self) -> None:
        CacheManager._PKL_PATH = self._original_pkl_path
        tmp_pkl = self._tmp_dir / "internal_data.pkl"
        if tmp_pkl.exists():
            tmp_pkl.unlink()


# ---------------------------------------------------------------------------
# 1. Initial state for new fields
# ---------------------------------------------------------------------------

class TestV3InitialState(_CacheManagerTestBase):
    """Fresh CacheManager must provide valid defaults for v3 fields."""

    def test_initial_constraint_settings_is_all_disabled(self) -> None:
        cache = CacheManager()
        settings = cache.get_constraint_settings()
        self.assertIsInstance(settings, SchedulingConstraintSettings)
        for ct in ThresholdConstraintType:
            self.assertFalse(settings.constraints[ct].enabled)

    def test_initial_ranking_settings_has_empty_priority_list(self) -> None:
        cache = CacheManager()
        settings = cache.get_ranking_settings()
        self.assertIsInstance(settings, RankingSettings)
        self.assertEqual(settings.priority_list, [])


# ---------------------------------------------------------------------------
# 2. set/get round-trips for new fields (RAM only)
# ---------------------------------------------------------------------------

class TestV3RamStorage(_CacheManagerTestBase):
    """Setters store data; getters retrieve the same object from RAM."""

    def test_set_and_get_constraint_settings(self) -> None:
        cache = CacheManager()
        new_settings = _make_constraint_settings(gap_k=5)

        cache.set_constraint_settings(new_settings)

        retrieved = cache.get_constraint_settings()
        self.assertIs(retrieved, new_settings)

    def test_set_and_get_ranking_settings(self) -> None:
        cache = CacheManager()
        new_settings = _make_ranking_settings()

        cache.set_ranking_settings(new_settings)

        retrieved = cache.get_ranking_settings()
        self.assertIs(retrieved, new_settings)


# ---------------------------------------------------------------------------
# 3. Smart cache invalidation
# ---------------------------------------------------------------------------

class TestSmartCacheInvalidation(_CacheManagerTestBase):
    """Verify the two-rule invalidation contract."""

    # --- set_constraint_settings must invalidate generated AND ranked ---

    def test_constraint_change_clears_generated_schedules(self) -> None:
        cache = CacheManager()
        cache.set_generated_schedules([_make_exam_system()])
        self.assertEqual(len(cache.get_generated_schedules()), 1)

        cache.set_constraint_settings(_make_constraint_settings())

        self.assertEqual(cache.get_generated_schedules(), [])

    def test_constraint_change_clears_ranked_schedules(self) -> None:
        cache = CacheManager()
        cache.set_generated_schedules([_make_exam_system()])
        # Manually place ranked schedules to simulate a prior ranking run.
        cache._state.ranked_schedules = ["dummy_ranked"]  # type: ignore[list-item]
        cache._persist()

        cache.set_constraint_settings(_make_constraint_settings())

        self.assertEqual(cache.get_ranked_schedules(), [])

    def test_constraint_change_persists_new_settings(self) -> None:
        cache = CacheManager()
        new_settings = _make_constraint_settings(gap_k=7)

        cache.set_constraint_settings(new_settings)

        # Settings must survive despite the invalidation side effects.
        retrieved = cache.get_constraint_settings()
        self.assertIs(retrieved, new_settings)

    # --- set_ranking_settings must invalidate ONLY ranked schedules ---

    def test_ranking_change_clears_ranked_schedules(self) -> None:
        cache = CacheManager()
        cache._state.ranked_schedules = ["dummy_ranked"]  # type: ignore[list-item]
        cache._persist()

        cache.set_ranking_settings(_make_ranking_settings())

        self.assertEqual(cache.get_ranked_schedules(), [])

    def test_ranking_change_preserves_generated_schedules(self) -> None:
        """This is the key rule: ranking changes must NOT wipe generated schedules."""
        cache = CacheManager()
        cache.set_generated_schedules([_make_exam_system()])

        cache.set_ranking_settings(_make_ranking_settings())

        # Generated schedules must be intact.
        self.assertEqual(len(cache.get_generated_schedules()), 1)

    def test_ranking_change_persists_new_ranking_settings(self) -> None:
        cache = CacheManager()
        new_ranking = _make_ranking_settings()

        cache.set_ranking_settings(new_ranking)

        self.assertIs(cache.get_ranking_settings(), new_ranking)

    # --- invalidate_generated_schedules must also clear ranked schedules ---

    def test_invalidate_generated_also_clears_ranked(self) -> None:
        cache = CacheManager()
        cache.set_generated_schedules([_make_exam_system()])
        cache._state.ranked_schedules = ["dummy_ranked"]  # type: ignore[list-item]
        cache._persist()

        cache.invalidate_generated_schedules()

        self.assertEqual(cache.get_generated_schedules(), [])
        self.assertEqual(cache.get_ranked_schedules(), [])

    # --- invalidate_ranked_schedules must NOT clear generated schedules ---

    def test_invalidate_ranked_preserves_generated(self) -> None:
        cache = CacheManager()
        cache.set_generated_schedules([_make_exam_system()])
        cache._state.ranked_schedules = ["dummy_ranked"]  # type: ignore[list-item]
        cache._persist()

        cache.invalidate_ranked_schedules()

        self.assertEqual(len(cache.get_generated_schedules()), 1)
        self.assertEqual(cache.get_ranked_schedules(), [])


# ---------------------------------------------------------------------------
# 4. Pickle round-trips for new v3 fields
# ---------------------------------------------------------------------------

class TestV3RoundTrip(_CacheManagerTestBase):
    """New fields survive save→reload correctly."""

    def test_constraint_settings_round_trip(self) -> None:
        first = CacheManager()
        saved = _make_constraint_settings(gap_k=4)
        first.set_constraint_settings(saved)

        second = CacheManager()

        loaded = second.get_constraint_settings()
        self.assertIsInstance(loaded, SchedulingConstraintSettings)
        gap = loaded.constraints[ThresholdConstraintType.mandatory_gap_days]
        self.assertTrue(gap.enabled)
        self.assertEqual(gap.k, 4)

    def test_ranking_settings_round_trip(self) -> None:
        first = CacheManager()
        saved = _make_ranking_settings()
        first.set_ranking_settings(saved)

        second = CacheManager()

        loaded = second.get_ranking_settings()
        self.assertIsInstance(loaded, RankingSettings)
        self.assertEqual(len(loaded.priority_list), 1)
        self.assertEqual(
            loaded.priority_list[0].criterion,
            RankingCriterion.min_mandatory_gap,
        )

    def test_full_v3_round_trip_all_fields(self) -> None:
        """All six state fields survive a complete save→reload cycle."""
        first = CacheManager()
        first.set_courses([_make_course()])
        first.set_exam_periods([_make_exam_period()])
        first.set_selected_programs(["83101"])
        first.set_constraint_settings(_make_constraint_settings(gap_k=2))
        first.set_ranking_settings(_make_ranking_settings())
        # set_constraint_settings wiped schedules above; re-add them.
        first.set_generated_schedules([_make_exam_system()])

        second = CacheManager()

        self.assertEqual(len(second.get_courses()), 1)
        self.assertEqual(len(second.get_exam_periods()), 1)
        self.assertEqual(second.get_selected_programs(), ["83101"])
        self.assertEqual(len(second.get_generated_schedules()), 1)
        gap = second.get_constraint_settings().constraints[
            ThresholdConstraintType.mandatory_gap_days
        ]
        self.assertTrue(gap.enabled)
        self.assertEqual(gap.k, 2)
        self.assertEqual(len(second.get_ranking_settings().priority_list), 1)

    def test_v3_sentinel_is_written_to_disk(self) -> None:
        """After any write the pickle must carry the v3 sentinel."""
        cache = CacheManager()
        cache.set_constraint_settings(_make_constraint_settings())

        with CacheManager._PKL_PATH.open("rb") as fh:
            state = pickle.load(fh)

        self.assertEqual(state.sentinel, _SENTINEL)


# ---------------------------------------------------------------------------
# 5. v2 backward compatibility
# ---------------------------------------------------------------------------

class TestV2BackwardCompatibility(_CacheManagerTestBase):
    """Old v2 pickle files must load without crashing."""

    def _write_v2_pickle(self, **extra_fields) -> None:
        """
        Write a minimal v2 _CacheState pickle to the tmp file.

        The v2 state does NOT have constraint_settings or ranking_settings.
        Additional keyword arguments are set as attributes on the state object
        to allow tests to inject courses, schedules, etc.
        """
        state = _CacheState.__new__(_CacheState)
        # Inject only the v2 fields manually.
        state.sentinel = _SENTINEL_V2
        state.courses = []
        state.exam_periods = []
        state.selected_programs = []
        state.generated_schedules = []
        state.ranked_schedules = []
        # v3 fields deliberately absent to simulate a real v2 file.
        for key, value in extra_fields.items():
            setattr(state, key, value)

        with CacheManager._PKL_PATH.open("wb") as fh:
            pickle.dump(state, fh)

    def test_v2_file_does_not_crash_on_load(self) -> None:
        self._write_v2_pickle()
        try:
            CacheManager()
        except Exception as exc:
            self.fail(f"Loading a v2 pickle raised: {exc}")

    def test_v2_file_provides_default_constraint_settings(self) -> None:
        self._write_v2_pickle()
        cache = CacheManager()
        settings = cache.get_constraint_settings()
        self.assertIsInstance(settings, SchedulingConstraintSettings)
        for ct in ThresholdConstraintType:
            self.assertFalse(settings.constraints[ct].enabled)

    def test_v2_file_provides_default_ranking_settings(self) -> None:
        self._write_v2_pickle()
        cache = CacheManager()
        settings = cache.get_ranking_settings()
        self.assertIsInstance(settings, RankingSettings)
        self.assertEqual(settings.priority_list, [])

    def test_v2_file_preserves_existing_courses(self) -> None:
        """Data stored in v2 fields is not lost during up-migration."""
        course = _make_course("Legacy Course", "00001")
        self._write_v2_pickle(courses=[course])
        cache = CacheManager()
        result = cache.get_courses()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Legacy Course")

    def test_v2_file_preserves_existing_selected_programs(self) -> None:
        self._write_v2_pickle(selected_programs=["83101", "83108"])
        cache = CacheManager()
        self.assertEqual(cache.get_selected_programs(), ["83101", "83108"])

    def test_v2_file_sentinel_upgraded_after_next_write(self) -> None:
        """
        After loading a v2 file and performing any write, the sentinel on disk
        must be the v3 value so that subsequent loads follow the v3 path.
        """
        self._write_v2_pickle()
        cache = CacheManager()

        # Any write re-serialises the state.
        cache.set_selected_programs(["83101"])

        with CacheManager._PKL_PATH.open("rb") as fh:
            state = pickle.load(fh)
        self.assertEqual(state.sentinel, _SENTINEL)

    def test_v2_then_reload_uses_v3_path(self) -> None:
        """
        A second load of the same file (now sentinel=v3 after first write)
        follows the v3 code path and still returns correct data.
        """
        self._write_v2_pickle(courses=[_make_course("Persistent", "11111")])
        first = CacheManager()
        # First write upgrades sentinel on disk.
        first.set_selected_programs(["83101"])

        second = CacheManager()

        self.assertEqual(len(second.get_courses()), 1)
        self.assertEqual(second.get_courses()[0].name, "Persistent")
        self.assertEqual(second.get_selected_programs(), ["83101"])
        # v3 defaults are present.
        self.assertIsInstance(second.get_constraint_settings(), SchedulingConstraintSettings)


# ---------------------------------------------------------------------------
# 6. Corrupted / incompatible pickle
# ---------------------------------------------------------------------------

class TestCorruptedPickle(_CacheManagerTestBase):
    """Unreadable or incompatible pickle files must fall back cleanly."""

    def test_garbled_bytes_fall_back_to_clean_state(self) -> None:
        CacheManager._PKL_PATH.write_bytes(b"\x00\xff\xfe garbage")
        try:
            cache = CacheManager()
        except Exception as exc:
            self.fail(f"Garbled pickle raised: {exc}")
        self.assertEqual(cache.get_courses(), [])
        self.assertIsInstance(cache.get_constraint_settings(), SchedulingConstraintSettings)

    def test_unknown_sentinel_falls_back_to_clean_state(self) -> None:
        state = _CacheState.__new__(_CacheState)
        state.sentinel = "CacheManager_future_v99"
        state.courses = [_make_course()]
        with CacheManager._PKL_PATH.open("wb") as fh:
            pickle.dump(state, fh)

        cache = CacheManager()

        # Unrecognised sentinel → clean state → courses must be empty.
        self.assertEqual(cache.get_courses(), [])

    def test_non_cache_state_object_falls_back_to_clean_state(self) -> None:
        with CacheManager._PKL_PATH.open("wb") as fh:
            pickle.dump({"key": "value"}, fh)

        cache = CacheManager()

        self.assertEqual(cache.get_courses(), [])


# ---------------------------------------------------------------------------
# 7. clear() resets v3 fields
# ---------------------------------------------------------------------------

class TestClearResetsV3Fields(_CacheManagerTestBase):
    """clear() must reset new settings fields to their defaults."""

    def test_clear_resets_constraint_settings_to_default(self) -> None:
        cache = CacheManager()
        cache.set_constraint_settings(_make_constraint_settings())
        cache.clear()

        restored = CacheManager()
        settings = restored.get_constraint_settings()
        for ct in ThresholdConstraintType:
            self.assertFalse(settings.constraints[ct].enabled)

    def test_clear_resets_ranking_settings_to_empty(self) -> None:
        cache = CacheManager()
        cache.set_ranking_settings(_make_ranking_settings())
        # set_ranking_settings wipes ranked_schedules; re-set constraint
        # settings to wipe generated_schedules so clear() starts fresh.
        cache.clear()

        restored = CacheManager()
        self.assertEqual(restored.get_ranking_settings().priority_list, [])

    def test_clear_deletes_pkl_file(self) -> None:
        cache = CacheManager()
        cache.set_constraint_settings(_make_constraint_settings())
        self.assertTrue(CacheManager._PKL_PATH.exists())

        cache.clear()

        self.assertFalse(CacheManager._PKL_PATH.exists())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
