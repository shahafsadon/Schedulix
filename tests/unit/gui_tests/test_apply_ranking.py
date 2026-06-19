"""Unit tests for ScheduleNavigationPresenter.apply_ranking().

Tests verify:
- Default presenter starts with no-op ranking.
- apply_ranking() re-sorts the buffer using the new settings.
- apply_ranking() resets the navigation index to 0.
- apply_ranking() with no-op settings keeps original order (only resets index).
- current_ranking() returns the most recently applied settings.
- Generation is never restarted (buffer mutation only).
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
from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter


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
    """One-period system with one exam per date."""
    exams = [
        ScheduledExam(course=_make_course(f"9{i:04d}"), exam_date=d)
        for i, d in enumerate(exam_dates)
    ]
    return ExamSystem(
        period_schedules=[ExamSchedule("FALL", "Aleph", exams)]
    )


class ApplyRankingTests(unittest.TestCase):
    """Behaviour of ScheduleNavigationPresenter.apply_ranking()."""

    def test_default_ranking_is_noop(self) -> None:
        """A fresh presenter has no-op ranking settings."""
        presenter = ScheduleNavigationPresenter([_make_system(date(2026, 1, 1))])
        self.assertTrue(presenter.current_ranking().is_noop())

    def test_apply_ranking_resets_index_to_zero(self) -> None:
        """After navigating to position 2, apply_ranking must reset to position 1."""
        s1 = _make_system(date(2026, 1, 1))
        s2 = _make_system(date(2026, 1, 2))
        presenter = ScheduleNavigationPresenter([s1, s2])

        presenter.next()
        self.assertEqual(presenter.position(), 2)

        presenter.apply_ranking(RankingSettings.default())
        self.assertEqual(presenter.position(), 1)

    def test_apply_ranking_sorts_by_fewer_exam_days(self) -> None:
        """FEWER_EXAM_DAYS brings systems with fewer distinct days to the front."""
        # s_many: 3 distinct days → should be pushed to the back.
        s_many = _make_system(date(2026, 2, 1), date(2026, 2, 5), date(2026, 2, 10))
        # s_few:  1 distinct day → should come first.
        s_few = _make_system(date(2026, 3, 1))

        presenter = ScheduleNavigationPresenter([s_many, s_few])
        # Before ranking: s_many is shown first (generation order).
        self.assertIs(presenter.current_system(), s_many)

        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        presenter.apply_ranking(settings)

        # After ranking: s_few (1 day) must be shown first.
        self.assertIs(presenter.current_system(), s_few)
        self.assertEqual(presenter.position(), 1)

    def test_apply_ranking_sorts_by_more_spread(self) -> None:
        """MORE_SPREAD brings systems with wider exam span to the front."""
        # s_narrow: span = 1 day
        s_narrow = _make_system(date(2026, 1, 1), date(2026, 1, 2))
        # s_wide:   span = 20 days
        s_wide = _make_system(date(2026, 1, 1), date(2026, 1, 21))

        presenter = ScheduleNavigationPresenter([s_narrow, s_wide])
        settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        presenter.apply_ranking(settings)

        # Wider span (s_wide) must appear first.
        self.assertIs(presenter.current_system(), s_wide)

    def test_apply_ranking_sorts_by_earlier_start(self) -> None:
        """EARLIER_START brings systems with an earlier first exam to the front."""
        s_late = _make_system(date(2026, 3, 15))
        s_early = _make_system(date(2026, 1, 5))

        presenter = ScheduleNavigationPresenter([s_late, s_early])
        settings = RankingSettings.build([RankingCriterion.EARLIER_START])
        presenter.apply_ranking(settings)

        self.assertIs(presenter.current_system(), s_early)

    def test_apply_noop_ranking_preserves_current_order(self) -> None:
        """Applying no-op settings must not change the buffer order."""
        s_a = _make_system(date(2026, 5, 1))
        s_b = _make_system(date(2026, 6, 1))

        presenter = ScheduleNavigationPresenter([s_a, s_b])
        presenter.apply_ranking(RankingSettings.default())

        # Generation order is unchanged; s_a is still first.
        self.assertIs(presenter.current_system(), s_a)

    def test_current_ranking_reflects_applied_settings(self) -> None:
        """current_ranking() returns the settings from the last apply_ranking() call."""
        presenter = ScheduleNavigationPresenter([_make_system(date(2026, 1, 1))])
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        presenter.apply_ranking(settings)
        self.assertIs(presenter.current_ranking(), settings)

    def test_apply_ranking_on_empty_buffer_does_not_raise(self) -> None:
        """apply_ranking() on an empty schedule list must not raise."""
        presenter = ScheduleNavigationPresenter([])
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        try:
            presenter.apply_ranking(settings)
        except Exception as exc:
            self.fail(f"apply_ranking() raised unexpectedly: {exc}")

    def test_sequential_apply_ranking_can_change_order_again(self) -> None:
        """apply_ranking() can be called multiple times to change ranking live."""
        # s_few: 1 day (wins on FEWER_EXAM_DAYS)
        s_few = _make_system(date(2026, 1, 1))
        # s_early: starts earlier (wins on EARLIER_START)
        s_early = _make_system(date(2025, 12, 1), date(2025, 12, 10))

        presenter = ScheduleNavigationPresenter([s_few, s_early])

        # First ranking: fewer days → s_few comes first
        presenter.apply_ranking(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        self.assertIs(presenter.current_system(), s_few)

        # Change ranking to earlier start → s_early comes first
        presenter.apply_ranking(RankingSettings.build([RankingCriterion.EARLIER_START]))
        self.assertIs(presenter.current_system(), s_early)

    def test_total_count_is_unchanged_after_ranking(self) -> None:
        """Re-ranking must not add or remove systems from the buffer."""
        systems = [_make_system(date(2026, i, 1)) for i in range(1, 6)]
        presenter = ScheduleNavigationPresenter(systems)
        self.assertEqual(presenter.total(), 5)

        presenter.apply_ranking(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        self.assertEqual(presenter.total(), 5)


if __name__ == "__main__":
    unittest.main()
