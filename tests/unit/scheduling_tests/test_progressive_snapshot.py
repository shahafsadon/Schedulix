"""Unit tests for ProgressiveRankedSnapshot (scheduling/progressiveSnapshot.py).

Covers:
- PARTIAL factory produces correct state.
- COMPLETE factory produces correct state.
- is_complete / is_partial predicates.
- with_ranking() re-sorts without mutating the original.
- with_ranking() preserves PARTIAL / COMPLETE state across re-ranking.
- with_ranking() with no-op settings leaves order unchanged.
"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from models import Course, ProgramEnrollment
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.rankingSettings import RankingCriterion, RankingSettings
from scheduling.progressiveSnapshot import (
    ProgressiveRankedSnapshot,
    SnapshotState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _course(number: str) -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def _system(*exam_dates: date) -> ExamSystem:
    exams = [
        ScheduledExam(course=_course(f"9{i:04d}"), exam_date=d)
        for i, d in enumerate(exam_dates)
    ]
    return ExamSystem(
        period_schedules=[ExamSchedule("FALL", "Aleph", exams)]
    )


_NOOP = RankingSettings.default()
_FEWER = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
_EARLIER = RankingSettings.build([RankingCriterion.EARLIER_START])


class SnapshotStateTests(unittest.TestCase):
    """Factory methods and state predicates."""

    def test_partial_factory_sets_partial_state(self) -> None:
        s = _system(date(2026, 1, 1))
        snap = ProgressiveRankedSnapshot.partial([s], _NOOP)
        self.assertIs(snap.state, SnapshotState.PARTIAL)
        self.assertTrue(snap.is_partial)
        self.assertFalse(snap.is_complete)

    def test_complete_factory_sets_complete_state(self) -> None:
        s = _system(date(2026, 1, 1))
        snap = ProgressiveRankedSnapshot.complete([s], _NOOP)
        self.assertIs(snap.state, SnapshotState.COMPLETE)
        self.assertTrue(snap.is_complete)
        self.assertFalse(snap.is_partial)

    def test_partial_snapshot_must_not_be_written_to_cache(self) -> None:
        """PARTIAL.is_complete must be False — enforcing the cache-write gate."""
        snap = ProgressiveRankedSnapshot.partial([], _NOOP)
        self.assertFalse(snap.is_complete)

    def test_schedules_are_copied_not_shared(self) -> None:
        """Mutating the original list must not affect the snapshot."""
        original = [_system(date(2026, 1, 1))]
        snap = ProgressiveRankedSnapshot.complete(original, _NOOP)
        original.clear()
        self.assertEqual(len(snap.schedules), 1)


class WithRankingTests(unittest.TestCase):
    """with_ranking() correctness."""

    def test_with_ranking_returns_new_instance(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([], _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertIsNot(snap, ranked)

    def test_with_ranking_preserves_complete_state(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([], _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertTrue(ranked.is_complete)

    def test_with_ranking_preserves_partial_state(self) -> None:
        """Re-ranking a PARTIAL snapshot must not promote it to COMPLETE."""
        snap = ProgressiveRankedSnapshot.partial([], _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertTrue(ranked.is_partial)

    def test_with_ranking_sorts_by_fewer_days(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 5), date(2026, 2, 10))
        s_few  = _system(date(2026, 3, 1))
        snap = ProgressiveRankedSnapshot.complete([s_many, s_few], _NOOP)
        ranked = snap.with_ranking(_FEWER)
        self.assertIs(ranked.schedules[0], s_few)

    def test_with_noop_preserves_order(self) -> None:
        s1 = _system(date(2026, 1, 1))
        s2 = _system(date(2026, 2, 1))
        snap = ProgressiveRankedSnapshot.complete([s1, s2], _FEWER)
        ranked = snap.with_ranking(_NOOP)
        self.assertIs(ranked.schedules[0], s1)
        self.assertIs(ranked.schedules[1], s2)

    def test_with_ranking_does_not_mutate_original(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 5))
        s_few  = _system(date(2026, 3, 1))
        snap = ProgressiveRankedSnapshot.complete([s_many, s_few], _NOOP)
        snap.with_ranking(_FEWER)          # discard result
        # Original order must be unchanged
        self.assertIs(snap.schedules[0], s_many)

    def test_with_ranking_updates_ranking_settings(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([], _NOOP)
        ranked = snap.with_ranking(_EARLIER)
        self.assertEqual(ranked.ranking_settings, _EARLIER)

    def test_with_ranking_empty_list_does_not_raise(self) -> None:
        snap = ProgressiveRankedSnapshot.complete([], _NOOP)
        try:
            ranked = snap.with_ranking(_FEWER)
        except Exception as exc:
            self.fail(f"with_ranking() raised unexpectedly: {exc}")
        self.assertEqual(ranked.schedules, [])


if __name__ == "__main__":
    unittest.main()
