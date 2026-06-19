"""Unit tests for CacheManager ranking-settings extensions (SCRUM-184).

Covers:
- set_ranking_settings / get_ranking_settings round-trip.
- invalidate_ranking_settings resets to no-op and persists.
- sentinel bump: v1 pickle is silently discarded → fresh state.
- ranking_settings field is preserved across a reload cycle.
- Other fields are unaffected by ranking-settings operations.
"""
import pickle
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager, _CacheState, _SENTINEL
from scheduling.rankingSettings import RankingCriterion, RankingSettings


# ---------------------------------------------------------------------------
# Helper that redirects the pickle to a temp dir per test
# ---------------------------------------------------------------------------

class _TmpCacheManager(CacheManager):
    pass  # _PKL_PATH is set per-instance in setUp


class CacheManagerRankingSettingsTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCacheManager._PKL_PATH = Path(self._tmp.name) / "test.pkl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # get / set
    # ------------------------------------------------------------------

    def test_get_ranking_settings_returns_noop_by_default(self) -> None:
        cache = _TmpCacheManager()
        self.assertTrue(cache.get_ranking_settings().is_noop())

    def test_set_and_get_ranking_settings(self) -> None:
        cache = _TmpCacheManager()
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        cache.set_ranking_settings(settings)
        self.assertEqual(cache.get_ranking_settings(), settings)

    def test_set_ranking_settings_persists_to_disk(self) -> None:
        cache = _TmpCacheManager()
        settings = RankingSettings.build([
            RankingCriterion.MORE_SPREAD,
            RankingCriterion.EARLIER_START,
        ])
        cache.set_ranking_settings(settings)
        # Reload from disk.
        cache2 = _TmpCacheManager()
        self.assertEqual(cache2.get_ranking_settings(), settings)

    def test_set_ranking_settings_does_not_clear_schedules(self) -> None:
        from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
        cache = _TmpCacheManager()
        system = ExamSystem(period_schedules=[
            ExamSchedule("FALL", "Aleph", [])
        ])
        cache.set_generated_schedules([system])
        cache.set_ranking_settings(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        # Schedules must be intact.
        self.assertEqual(len(cache.get_generated_schedules()), 1)

    # ------------------------------------------------------------------
    # invalidate
    # ------------------------------------------------------------------

    def test_invalidate_ranking_settings_resets_to_noop(self) -> None:
        cache = _TmpCacheManager()
        cache.set_ranking_settings(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        cache.invalidate_ranking_settings()
        self.assertTrue(cache.get_ranking_settings().is_noop())

    def test_invalidate_ranking_settings_persists(self) -> None:
        cache = _TmpCacheManager()
        cache.set_ranking_settings(RankingSettings.build([RankingCriterion.MORE_SPREAD]))
        cache.invalidate_ranking_settings()
        # Reload — must still see noop.
        cache2 = _TmpCacheManager()
        self.assertTrue(cache2.get_ranking_settings().is_noop())

    def test_invalidate_ranking_settings_does_not_clear_schedules(self) -> None:
        from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
        cache = _TmpCacheManager()
        cache.set_generated_schedules([ExamSystem(period_schedules=[
            ExamSchedule("FALL", "Aleph", [])
        ])])
        cache.set_ranking_settings(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        cache.invalidate_ranking_settings()
        self.assertEqual(len(cache.get_generated_schedules()), 1)

    # ------------------------------------------------------------------
    # Sentinel / migration
    # ------------------------------------------------------------------

    def test_sentinel_is_v2(self) -> None:
        """The sentinel must be CacheManager_v2 so v1 pickles are rejected."""
        self.assertEqual(_SENTINEL, "CacheManager_v2")

    def test_v1_pickle_is_discarded_silently(self) -> None:
        """A pickle written with the old v1 sentinel produces a clean state."""
        pkl_path = _TmpCacheManager._PKL_PATH

        # Manufacture a stale v1 state.
        stale = _CacheState()
        stale.sentinel = "CacheManager_v1"  # wrong version
        with pkl_path.open("wb") as fh:
            pickle.dump(stale, fh)

        # Loading must silently fall back to a clean state.
        cache = _TmpCacheManager()
        self.assertEqual(cache.get_courses(), [])
        self.assertEqual(cache.get_generated_schedules(), [])
        self.assertTrue(cache.get_ranking_settings().is_noop())

    def test_v2_pickle_is_loaded_correctly(self) -> None:
        """A valid v2 pickle round-trips all fields including ranking_settings."""
        cache = _TmpCacheManager()
        settings = RankingSettings.build([RankingCriterion.EARLIER_START])
        cache.set_ranking_settings(settings)

        cache2 = _TmpCacheManager()
        loaded = cache2.get_ranking_settings()
        self.assertEqual(loaded, settings)
        self.assertFalse(loaded.is_noop())


if __name__ == "__main__":
    unittest.main()
