"""test_ranking_edge_cases.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Edge case scenarios for progressive ranking (SCRUM-185).

Covers:
- Empty results: all components tolerate zero schedules gracefully.
- Single tiny batch (one system with one exam): correct sort key / no crash.
- Multiple large batches: the ranked buffer stays globally correct.
- Duplicate criteria in RankingSettings.build(): first occurrence wins.
- None values in criteria list: silently skipped.
- All criteria produce same key: stable insertion order preserved.
- Single criterion, single system: trivial but must not raise.
- System with no exams: sort keys return safe defaults.
- Ranking a single system produces a list of length 1.
- RankingSettings.is_noop() semantics.
- ProgressiveRankedSnapshot.with_ranking() on single-item list.
- SchedulingPresenter.generate() zero-result path does not overwrite cache.
- SchedulingPresenter.invalidate_for_threshold_change() leaves cache clean.

No GUI, no threads, no ``time.sleep()``.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

_SRC = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(_SRC))

from application.cache_manager import CacheManager
from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter
from gui.presenters.schedulingPresenter import SchedulingPresenter
from models import Course, ProgramEnrollment
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.rankingSettings import RankingCriterion, RankingSettings
from scheduling.progressiveSnapshot import ProgressiveRankedSnapshot, SnapshotState
from scheduling.schedulingService import SchedulingOutcome, SchedulingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _TmpCache(CacheManager):
    pass


def _course(n: str) -> Course:
    return Course(
        name=f"Course {n}",
        course_number=n,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def _system(*dates: date) -> ExamSystem:
    exams = [
        ScheduledExam(course=_course(f"7{i:04d}"), exam_date=d)
        for i, d in enumerate(dates)
    ]
    return ExamSystem(period_schedules=[ExamSchedule("FALL", "Aleph", exams)])


def _empty_system() -> ExamSystem:
    """ExamSystem with no scheduled exams."""
    return ExamSystem(period_schedules=[ExamSchedule("FALL", "Aleph", [])])


_FEWER   = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
_EARLIER = RankingSettings.build([RankingCriterion.EARLIER_START])
_SPREAD  = RankingSettings.build([RankingCriterion.MORE_SPREAD])
_NOOP    = RankingSettings.default()


# ---------------------------------------------------------------------------
# 1. Empty-results edge cases
# ---------------------------------------------------------------------------

class EmptyResultsTests(unittest.TestCase):
    """All components must tolerate an empty schedule list without crashing."""

    def test_snapshot_partial_empty_list(self) -> None:
        snap = ProgressiveRankedSnapshot.partial([], _NOOP)
        self.assertEqual(snap.schedules, [])
        self.assertTrue(snap.is_partial)

    def test_snapshot_complete_empty_list(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([], _NOOP)
        self.assertEqual(snap.schedules, [])
        self.assertTrue(snap.is_complete)

    def test_with_ranking_on_empty_snapshot_returns_empty(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([], _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertEqual(ranked.schedules, [])

    def test_navigation_presenter_empty_has_no_schedules(self) -> None:
        p = ScheduleNavigationPresenter([])
        self.assertFalse(p.has_schedules())
        self.assertIsNone(p.current_view())

    def test_navigation_presenter_apply_ranking_on_empty_does_not_crash(self) -> None:
        p = ScheduleNavigationPresenter([])
        for settings in [_FEWER, _EARLIER, _SPREAD, _NOOP]:
            try:
                p.apply_ranking(settings)
            except Exception as exc:
                self.fail(f"apply_ranking() raised on empty buffer: {exc}")

    def test_rerank_cached_on_empty_cache_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _TmpCache._PKL_PATH = Path(tmp) / "test.pkl"
            cache = _TmpCache()
            p = SchedulingPresenter(cache, service=MagicMock(spec=SchedulingService))
            self.assertFalse(p.rerank_cached(_FEWER))

    def test_ranking_settings_sort_key_empty_system(self) -> None:
        """sort_key() on a system with no exams must not raise."""
        s = _empty_system()
        for settings in [_FEWER, _EARLIER, _SPREAD]:
            try:
                key = settings.sort_key(s)
                self.assertIsInstance(key, tuple)
            except Exception as exc:
                self.fail(f"sort_key() raised on empty system: {exc}")


# ---------------------------------------------------------------------------
# 2. Single-batch / single-system edge cases
# ---------------------------------------------------------------------------

class SingleSystemTests(unittest.TestCase):
    """One system, possibly with a tiny date window."""

    def test_snapshot_with_single_system(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([_system(date(2026, 1, 1))], _NOOP)
        self.assertEqual(len(snap.schedules), 1)

    def test_with_ranking_single_system_returns_same_system(self) -> None:
        s = _system(date(2026, 1, 1))
        snap = ProgressiveRankedSnapshot.complete([s], _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertIs(ranked.schedules[0], s)

    def test_navigation_presenter_single_system_total_is_one(self) -> None:
        p = ScheduleNavigationPresenter([_system(date(2026, 1, 1))])
        self.assertEqual(p.total(), 1)
        self.assertEqual(p.position(), 1)

    def test_navigation_presenter_single_system_prev_next_stay_in_bounds(self) -> None:
        p = ScheduleNavigationPresenter([_system(date(2026, 1, 1))])
        p.next()        # must not raise or go out of bounds
        p.previous()    # must not raise
        self.assertEqual(p.position(), 1)

    def test_apply_ranking_on_single_system_resets_index(self) -> None:
        p = ScheduleNavigationPresenter([_system(date(2026, 1, 1))])
        p.apply_ranking(_FEWER)
        self.assertEqual(p.position(), 1)

    def test_sort_key_single_exam_day_system(self) -> None:
        s = _system(date(2026, 1, 1))
        for settings in [_FEWER, _EARLIER, _SPREAD]:
            key = settings.sort_key(s)
            self.assertIsInstance(key, tuple)
            self.assertEqual(len(key), len(settings.criteria))


# ---------------------------------------------------------------------------
# 3. Multiple large batches
# ---------------------------------------------------------------------------

class MultipleLargeBatchTests(unittest.TestCase):
    """100-system buffer: sort produces globally correct order."""

    def _make_systems(self, count: int, *, days_each: int = 1) -> list[ExamSystem]:
        return [
            _system(*[date(2026, 1, min(d + i, 28)) for d in range(1, days_each + 1)])
            for i in range(count)
        ]

    def test_fifty_systems_ranked_by_fewer_days(self) -> None:
        winner = _system(date(2026, 3, 1))              # 1 day
        rest   = self._make_systems(49, days_each=3)    # 3 days each
        snap = ProgressiveRankedSnapshot.complete([winner] + rest, _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertIs(ranked.schedules[0], winner)

    def test_hundred_systems_ranked_by_earlier_start(self) -> None:
        earliest = _system(date(2025, 12, 1))
        rest = [_system(date(2026, 1, 1))] * 99
        all_systems = rest + [earliest]
        snap = ProgressiveRankedSnapshot.complete(all_systems, _NOOP)
        ranked = snap.with_ranking(_EARLIER)
        self.assertIs(ranked.schedules[0], earliest)

    def test_batch_accumulation_100_systems(self) -> None:
        """Verify count and order across 10 batches of 10 systems each."""
        earliest = _system(date(2025, 11, 1))
        systems = [_system(date(2026, i % 12 + 1, 1)) for i in range(99)]
        all_batches = [systems[i:i+10] for i in range(0, 100, 10)]
        all_batches[-1].append(earliest)   # inject winner into last batch

        buffer: list[ExamSystem] = []
        for batch in all_batches:
            buffer.extend(batch)
        snap = ProgressiveRankedSnapshot.complete(buffer, _EARLIER)
        ranked = snap.with_ranking(_EARLIER)
        self.assertIs(ranked.schedules[0], earliest)
        self.assertEqual(len(ranked.schedules), 100)

    def test_stable_sort_same_key_preserves_relative_order(self) -> None:
        """Systems with identical sort keys must keep their relative order."""
        # All on the same date → all EARLIER_START keys are equal.
        systems = [_system(date(2026, 1, 1)) for _ in range(10)]
        snap = ProgressiveRankedSnapshot.complete(systems, _NOOP)
        ranked = snap.with_ranking(_EARLIER)
        # Stable sort: identities must be preserved in original relative order.
        for original, after_sort in zip(systems, ranked.schedules):
            self.assertIs(original, after_sort)


# ---------------------------------------------------------------------------
# 4. RankingSettings edge cases
# ---------------------------------------------------------------------------

class RankingSettingsEdgeCaseTests(unittest.TestCase):
    """Duplicate criteria, None values, is_noop, and empty criteria."""

    def test_duplicate_criteria_first_occurrence_wins(self) -> None:
        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.FEWER_EXAM_DAYS,   # duplicate
            RankingCriterion.EARLIER_START,
        ])
        self.assertEqual(settings.criteria, (
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.EARLIER_START,
        ))

    def test_none_values_silently_skipped(self) -> None:
        settings = RankingSettings.build([
            None,
            RankingCriterion.FEWER_EXAM_DAYS,
            None,
            RankingCriterion.EARLIER_START,
        ])
        self.assertEqual(settings.criteria, (
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.EARLIER_START,
        ))

    def test_all_none_produces_noop(self) -> None:
        settings = RankingSettings.build([None, None, None])
        self.assertTrue(settings.is_noop())

    def test_empty_list_produces_noop(self) -> None:
        settings = RankingSettings.build([])
        self.assertTrue(settings.is_noop())

    def test_default_is_noop(self) -> None:
        self.assertTrue(RankingSettings.default().is_noop())

    def test_non_empty_criteria_is_not_noop(self) -> None:
        settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        self.assertFalse(settings.is_noop())

    def test_all_three_criteria_no_duplicates(self) -> None:
        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.MORE_SPREAD,
            RankingCriterion.EARLIER_START,
        ])
        self.assertEqual(len(settings.criteria), 3)

    def test_all_criteria_duplicated_leaves_one_each(self) -> None:
        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.MORE_SPREAD,
            RankingCriterion.EARLIER_START,
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.MORE_SPREAD,
            RankingCriterion.EARLIER_START,
        ])
        self.assertEqual(len(settings.criteria), 3)

    def test_sort_key_length_matches_criteria_count(self) -> None:
        s = _system(date(2026, 1, 1))
        for criteria_list in [
            [],
            [RankingCriterion.FEWER_EXAM_DAYS],
            [RankingCriterion.FEWER_EXAM_DAYS, RankingCriterion.EARLIER_START],
            [RankingCriterion.FEWER_EXAM_DAYS, RankingCriterion.MORE_SPREAD, RankingCriterion.EARLIER_START],
        ]:
            settings = RankingSettings.build(criteria_list)
            key = settings.sort_key(s)
            self.assertEqual(len(key), len(settings.criteria))

    def test_frozen_dataclass_equality(self) -> None:
        s1 = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        s2 = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        self.assertEqual(s1, s2)

    def test_different_criteria_order_not_equal(self) -> None:
        s1 = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS, RankingCriterion.EARLIER_START])
        s2 = RankingSettings.build([RankingCriterion.EARLIER_START, RankingCriterion.FEWER_EXAM_DAYS])
        self.assertNotEqual(s1, s2)


# ---------------------------------------------------------------------------
# 5. SchedulingPresenter zero-result and invalidation edge cases
# ---------------------------------------------------------------------------

class SchedulingPresenterEdgeCaseTests(unittest.TestCase):
    """Edge behaviour in generate() and invalidate paths."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCache._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCache()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _svc(self, systems, relevant=3) -> SchedulingService:
        svc = MagicMock(spec=SchedulingService)
        svc.run.return_value = SchedulingOutcome(
            relevant_course_count=relevant,
            schedule_count=len(systems),
            schedules=systems,
        )
        return svc

    def test_generate_zero_results_does_not_overwrite_existing_cache(self) -> None:
        """A zero-result generation run must not clear previously cached schedules."""
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        svc = MagicMock(spec=SchedulingService)
        svc.run.return_value = SchedulingOutcome(
            relevant_course_count=3, schedule_count=0, schedules=[]
        )
        p = SchedulingPresenter(self._cache, service=svc)
        result = p.generate()
        self.assertTrue(result.success)
        self.assertEqual(result.schedule_count, 0)
        # Previous cache entry untouched.
        self.assertEqual(len(self._cache.get_generated_schedules()), 1)

    def test_generate_with_ranking_stores_sorted_result(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 10))
        s_few  = _system(date(2026, 3, 1))
        p = SchedulingPresenter(
            self._cache,
            service=self._svc([s_many, s_few]),
            initial_ranking=_FEWER,
        )
        p.generate()
        self.assertIs(self._cache.get_generated_schedules()[0], s_few)

    def test_invalidate_leaves_cache_empty_and_ranking_noop(self) -> None:
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        self._cache.set_ranking_settings(_FEWER)
        p = SchedulingPresenter(self._cache, initial_ranking=_FEWER)
        p.invalidate_for_threshold_change()
        self.assertEqual(self._cache.get_generated_schedules(), [])
        self.assertTrue(self._cache.get_ranking_settings().is_noop())

    def test_invalidate_then_generate_produces_fresh_result(self) -> None:
        """After invalidation, generate() produces and caches a new result."""
        s_fresh = _system(date(2026, 5, 1))
        p = SchedulingPresenter(
            self._cache,
            service=self._svc([s_fresh]),
        )
        p.invalidate_for_threshold_change()
        result = p.generate()
        self.assertTrue(result.success)
        self.assertEqual(len(self._cache.get_generated_schedules()), 1)

    def test_generate_value_error_does_not_touch_cache(self) -> None:
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        svc = MagicMock(spec=SchedulingService)
        svc.run.side_effect = ValueError("No courses loaded.")
        p = SchedulingPresenter(self._cache, service=svc)
        result = p.generate()
        self.assertFalse(result.success)
        # Cache must be unchanged.
        self.assertEqual(len(self._cache.get_generated_schedules()), 1)


if __name__ == "__main__":
    unittest.main()
