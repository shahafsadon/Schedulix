"""Unit tests for RankingSettings (scheduling/rankingSettings.py).

Tests cover:
- RankingCriterion enum values exist.
- RankingSettings.build() deduplicates and filters None values.
- RankingSettings.default() returns a no-op.
- sort_key() produces correct ordering for each criterion.
- is_noop() correctly reports the empty-criteria case.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_course(number: str) -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def _make_system(*exam_dates: date) -> ExamSystem:
    """Create a one-period ExamSystem with one exam per supplied date."""
    exams = [
        ScheduledExam(course=_make_course(f"8{i:04d}"), exam_date=d)
        for i, d in enumerate(exam_dates)
    ]
    return ExamSystem(
        period_schedules=[ExamSchedule(semester="FALL", moed="Aleph", scheduled_exams=exams)]
    )


class RankingSettingsBuildTests(unittest.TestCase):
    """RankingSettings.build() deduplication and None-filtering."""

    def test_build_empty_list_is_noop(self) -> None:
        settings = RankingSettings.build([])
        self.assertTrue(settings.is_noop())
        self.assertEqual(settings.criteria, ())

    def test_build_removes_duplicates_keeps_first_occurrence(self) -> None:
        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.EARLIER_START,
            RankingCriterion.FEWER_EXAM_DAYS,  # duplicate — should be dropped
        ])
        self.assertEqual(settings.criteria, (
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.EARLIER_START,
        ))

    def test_build_filters_none_values(self) -> None:
        settings = RankingSettings.build([
            None,
            RankingCriterion.MORE_SPREAD,
            None,
        ])
        self.assertEqual(settings.criteria, (RankingCriterion.MORE_SPREAD,))

    def test_build_all_none_is_noop(self) -> None:
        settings = RankingSettings.build([None, None])
        self.assertTrue(settings.is_noop())

    def test_build_preserves_order(self) -> None:
        criteria = [
            RankingCriterion.EARLIER_START,
            RankingCriterion.MORE_SPREAD,
            RankingCriterion.FEWER_EXAM_DAYS,
        ]
        settings = RankingSettings.build(criteria)
        self.assertEqual(list(settings.criteria), criteria)

    def test_default_is_noop(self) -> None:
        self.assertTrue(RankingSettings.default().is_noop())

    def test_is_noop_false_when_criteria_present(self) -> None:
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        self.assertFalse(settings.is_noop())


class RankingSettingsSortKeyTests(unittest.TestCase):
    """sort_key() produces the correct ordering for each criterion."""

    def test_noop_sort_key_is_empty_tuple(self) -> None:
        system = _make_system(date(2026, 2, 1))
        key = RankingSettings.default().sort_key(system)
        self.assertEqual(key, ())

    def test_fewer_exam_days_sorts_ascending(self) -> None:
        """System with fewer distinct exam days should sort first."""
        # System A: 2 distinct days
        system_a = _make_system(date(2026, 2, 1), date(2026, 2, 3))
        # System B: 3 distinct days
        system_b = _make_system(date(2026, 2, 1), date(2026, 2, 3), date(2026, 2, 5))

        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        sorted_systems = sorted([system_b, system_a], key=settings.sort_key)
        # A (2 days) must come first
        self.assertIs(sorted_systems[0], system_a)

    def test_more_spread_sorts_larger_span_first(self) -> None:
        """System with wider exam span should sort first."""
        # System A: span = (Feb 10) - (Feb 1) = 9 days
        system_a = _make_system(date(2026, 2, 1), date(2026, 2, 10))
        # System B: span = (Feb 3) - (Feb 1) = 2 days
        system_b = _make_system(date(2026, 2, 1), date(2026, 2, 3))

        settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        sorted_systems = sorted([system_b, system_a], key=settings.sort_key)
        # A (9-day span) must come first
        self.assertIs(sorted_systems[0], system_a)

    def test_earlier_start_sorts_earlier_date_first(self) -> None:
        """System whose first exam is earliest should sort first."""
        system_a = _make_system(date(2026, 1, 15))   # earlier start
        system_b = _make_system(date(2026, 2, 1))    # later start

        settings = RankingSettings.build([RankingCriterion.EARLIER_START])
        sorted_systems = sorted([system_b, system_a], key=settings.sort_key)
        self.assertIs(sorted_systems[0], system_a)

    def test_composite_sort_key_uses_tiebreaker(self) -> None:
        """When the primary key ties, the secondary key is the tiebreaker."""
        # Both systems have 2 distinct exam days (primary key ties)
        # System A starts Jan 20, system B starts Jan 25
        system_a = _make_system(date(2026, 1, 20), date(2026, 1, 25))
        system_b = _make_system(date(2026, 1, 25), date(2026, 1, 30))

        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.EARLIER_START,
        ])
        sorted_systems = sorted([system_b, system_a], key=settings.sort_key)
        # Primary key ties (both 2 days); A has earlier start → A first
        self.assertIs(sorted_systems[0], system_a)

    def test_system_with_no_exams_does_not_raise(self) -> None:
        """A system with no scheduled exams should not crash sort_key."""
        system = _make_system()   # no exam dates
        settings = RankingSettings.build([
            RankingCriterion.FEWER_EXAM_DAYS,
            RankingCriterion.MORE_SPREAD,
            RankingCriterion.EARLIER_START,
        ])
        # Should not raise; just return a tuple with sensible defaults
        key = settings.sort_key(system)
        self.assertIsInstance(key, tuple)


if __name__ == "__main__":
    unittest.main()
