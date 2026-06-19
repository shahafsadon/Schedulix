"""test_ranked_buffer.py
~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for batch-accumulation and ranked-buffer merge logic (SCRUM-185).

These tests target the pure domain objects — ``ProgressiveRankedSnapshot``,
``RankingSettings``, and ``RankingCriterion`` — and the pattern of
incrementally accumulating batches into a ranked buffer.

No GUI, no threads, no ``time.sleep()``.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(_SRC))

from models import Course, ProgramEnrollment
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.rankingSettings import RankingCriterion, RankingSettings
from scheduling.progressiveSnapshot import ProgressiveRankedSnapshot, SnapshotState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        ScheduledExam(course=_course(f"9{i:04d}"), exam_date=d)
        for i, d in enumerate(dates)
    ]
    return ExamSystem(period_schedules=[ExamSchedule("FALL", "Aleph", exams)])


def _simulate_batch_merge(
    batches: list[list[ExamSystem]],
    settings: RankingSettings,
) -> list[ExamSystem]:
    """
    Simulate the progressive accumulate-and-rank pattern used by the service.

    Each batch arrives independently (mimicking a background iterator).
    After each batch the buffer is re-ranked with *settings* and returned as a
    new PARTIAL snapshot.  Only the final call produces a COMPLETE snapshot.
    """
    buffer: list[ExamSystem] = []
    snap: ProgressiveRankedSnapshot | None = None

    for i, batch in enumerate(batches):
        buffer.extend(batch)
        is_last = (i == len(batches) - 1)
        if is_last:
            snap = ProgressiveRankedSnapshot.complete(buffer, settings)
        else:
            snap = ProgressiveRankedSnapshot.partial(buffer, settings)
        snap = snap.with_ranking(settings)

    return snap.schedules if snap else []


# ---------------------------------------------------------------------------
# Batch iterator / merge tests
# ---------------------------------------------------------------------------

class BatchAccumulationTests(unittest.TestCase):
    """Verify that batches accumulate correctly into a growing buffer."""

    def test_single_batch_produces_correct_count(self) -> None:
        batch = [_system(date(2026, 1, d)) for d in range(1, 4)]
        result = _simulate_batch_merge([batch], RankingSettings.default())
        self.assertEqual(len(result), 3)

    def test_two_batches_accumulate_all_systems(self) -> None:
        b1 = [_system(date(2026, 1, 1)), _system(date(2026, 1, 2))]
        b2 = [_system(date(2026, 2, 1)), _system(date(2026, 2, 2))]
        result = _simulate_batch_merge([b1, b2], RankingSettings.default())
        self.assertEqual(len(result), 4)

    def test_five_batches_of_varying_size_accumulate(self) -> None:
        batches = [[_system(date(2026, i, 1))] * i for i in range(1, 6)]
        # 1 + 2 + 3 + 4 + 5 = 15 total systems
        result = _simulate_batch_merge(batches, RankingSettings.default())
        self.assertEqual(len(result), 15)

    def test_empty_batch_does_not_duplicate_existing_systems(self) -> None:
        b1 = [_system(date(2026, 1, 1)), _system(date(2026, 1, 2))]
        b2: list[ExamSystem] = []      # empty batch
        b3 = [_system(date(2026, 3, 1))]
        result = _simulate_batch_merge([b1, b2, b3], RankingSettings.default())
        self.assertEqual(len(result), 3)

    def test_noop_ranking_preserves_insertion_order(self) -> None:
        """With no-op ranking the buffer order must match insertion order."""
        s1 = _system(date(2026, 3, 1))
        s2 = _system(date(2026, 1, 1))
        s3 = _system(date(2026, 2, 1))
        result = _simulate_batch_merge([[s1], [s2], [s3]], RankingSettings.default())
        self.assertIs(result[0], s1)
        self.assertIs(result[1], s2)
        self.assertIs(result[2], s3)


# ---------------------------------------------------------------------------
# Ranked buffer sort correctness across batches
# ---------------------------------------------------------------------------

class RankedBufferMergeTests(unittest.TestCase):
    """Re-sorting a growing buffer produces the globally correct order."""

    def test_fewer_days_ranking_applies_to_merged_buffer(self) -> None:
        """After merging, the final order must reflect FEWER_EXAM_DAYS globally."""
        # Batch 1: one system with 3 exam days.
        s_many = _system(date(2026, 2, 1), date(2026, 2, 5), date(2026, 2, 10))
        # Batch 2: one system with 1 exam day.
        s_few = _system(date(2026, 3, 1))
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        result = _simulate_batch_merge([[s_many], [s_few]], settings)
        self.assertIs(result[0], s_few)

    def test_earlier_start_ranking_across_batches(self) -> None:
        s_late  = _system(date(2026, 5, 1))
        s_early = _system(date(2026, 1, 1))
        settings = RankingSettings.build([RankingCriterion.EARLIER_START])
        result = _simulate_batch_merge([[s_late], [s_early]], settings)
        self.assertIs(result[0], s_early)

    def test_more_spread_ranking_across_batches(self) -> None:
        s_narrow = _system(date(2026, 1, 1), date(2026, 1, 2))
        s_wide   = _system(date(2026, 1, 1), date(2026, 2, 28))
        settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        result = _simulate_batch_merge([[s_narrow], [s_wide]], settings)
        self.assertIs(result[0], s_wide)

    def test_composite_ranking_tiebreaker_respected(self) -> None:
        """Primary key tie resolved by tiebreaker across batch boundary."""
        # Both have 2 distinct exam days — FEWER_EXAM_DAYS ties.
        # Tiebreaker: EARLIER_START — s_a starts earlier.
        s_a = _system(date(2026, 1, 10), date(2026, 1, 15))   # earlier
        s_b = _system(date(2026, 2, 10), date(2026, 2, 15))   # later
        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.EARLIER_START,
        ])
        result = _simulate_batch_merge([[s_b], [s_a]], settings)
        self.assertIs(result[0], s_a)

    def test_large_batch_followed_by_small_batch_stays_sorted(self) -> None:
        """When a large first batch arrives, a smaller second batch integrates."""
        big_batch = [_system(date(2026, i, 1)) for i in range(1, 10)]
        # Last system starts earliest — must float to front after re-rank.
        winner = _system(date(2025, 12, 1))
        settings = RankingSettings.build([RankingCriterion.EARLIER_START])
        result = _simulate_batch_merge([big_batch, [winner]], settings)
        self.assertIs(result[0], winner)

    def test_ranking_change_between_batches_reorders_globally(self) -> None:
        """Simulates dynamic ranking change mid-generation."""
        s_few  = _system(date(2026, 1, 1))                              # 1 day
        s_wide = _system(date(2026, 1, 1), date(2026, 3, 31))           # wide spread

        # After batch 1, we rank by FEWER_EXAM_DAYS — s_few wins.
        snap1 = ProgressiveRankedSnapshot.partial(
            [s_few, s_wide],
            RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]),
        ).with_ranking(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        self.assertIs(snap1.schedules[0], s_few)

        # User changes ranking to MORE_SPREAD — s_wide must now win.
        new_settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        snap2 = snap1.with_ranking(new_settings)
        self.assertIs(snap2.schedules[0], s_wide)
        # State must still be PARTIAL (not promoted to COMPLETE by re-ranking).
        self.assertTrue(snap2.is_partial)


# ---------------------------------------------------------------------------
# PARTIAL / COMPLETE gate across batch boundaries
# ---------------------------------------------------------------------------

class SnapshotStateAcrossBatchesTests(unittest.TestCase):
    """PARTIAL/COMPLETE invariant is preserved when batches arrive."""

    def test_intermediate_snapshots_are_partial(self) -> None:
        """Every non-final snapshot produced during accumulation must be PARTIAL."""
        batches = [[_system(date(2026, i, 1))] for i in range(1, 5)]
        buffer: list[ExamSystem] = []
        settings = RankingSettings.default()
        for i, batch in enumerate(batches[:-1]):   # all except last
            buffer.extend(batch)
            snap = ProgressiveRankedSnapshot.partial(buffer, settings)
            self.assertTrue(snap.is_partial,
                            f"Snapshot after batch {i} must be PARTIAL")
            self.assertFalse(snap.is_complete)

    def test_final_snapshot_is_complete(self) -> None:
        """Only the snapshot produced after the last batch is COMPLETE."""
        buffer = [_system(date(2026, 1, 1)), _system(date(2026, 2, 1))]
        snap = ProgressiveRankedSnapshot.complete(buffer, RankingSettings.default())
        self.assertTrue(snap.is_complete)

    def test_partial_snapshot_rewound_through_with_ranking_stays_partial(self) -> None:
        """Re-ranking a PARTIAL snapshot must never promote it to COMPLETE."""
        snap = ProgressiveRankedSnapshot.partial(
            [_system(date(2026, 1, 1))],
            RankingSettings.default(),
        )
        for _ in range(5):
            snap = snap.with_ranking(
                RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
            )
            self.assertTrue(snap.is_partial)


if __name__ == "__main__":
    unittest.main()
