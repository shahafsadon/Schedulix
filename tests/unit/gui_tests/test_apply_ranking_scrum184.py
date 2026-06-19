"""Unit tests for ScheduleNavigationPresenter SCRUM-184 additions.

Covers:
- initial_ranking is stored and returned by current_ranking().
- apply_ranking() re-sorts buffer, resets index.
- apply_ranking() fires on_ranking_changed callback with new settings.
- apply_ranking() does NOT fire callback when none was supplied.
- on_ranking_changed receives the exact settings object passed to apply_ranking().
- Sequential apply_ranking() calls change order live.
- apply_ranking() on empty buffer does not raise.
- total() is unchanged after ranking.
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
        ScheduledExam(course=_course(f"8{i:04d}"), exam_date=d)
        for i, d in enumerate(exam_dates)
    ]
    return ExamSystem(
        period_schedules=[ExamSchedule("FALL", "Aleph", exams)]
    )


_NOOP    = RankingSettings.default()
_FEWER   = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
_SPREAD  = RankingSettings.build([RankingCriterion.MORE_SPREAD])
_EARLIER = RankingSettings.build([RankingCriterion.EARLIER_START])


class InitialRankingTests(unittest.TestCase):
    """initial_ranking parameter behaviour."""

    def test_default_ranking_is_noop_when_not_supplied(self) -> None:
        presenter = ScheduleNavigationPresenter([_system(date(2026, 1, 1))])
        self.assertTrue(presenter.current_ranking().is_noop())

    def test_initial_ranking_is_stored(self) -> None:
        presenter = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1))],
            initial_ranking=_FEWER,
        )
        self.assertEqual(presenter.current_ranking(), _FEWER)

    def test_initial_ranking_none_falls_back_to_noop(self) -> None:
        presenter = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1))],
            initial_ranking=None,
        )
        self.assertTrue(presenter.current_ranking().is_noop())


class ApplyRankingCallbackTests(unittest.TestCase):
    """on_ranking_changed callback wiring."""

    def test_callback_is_fired_on_apply_ranking(self) -> None:
        received: list[RankingSettings] = []
        presenter = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1))],
            on_ranking_changed=received.append,
        )
        presenter.apply_ranking(_FEWER)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], _FEWER)

    def test_callback_receives_new_settings_not_old(self) -> None:
        received: list[RankingSettings] = []
        presenter = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1))],
            initial_ranking=_NOOP,
            on_ranking_changed=received.append,
        )
        presenter.apply_ranking(_EARLIER)
        self.assertIs(received[0], _EARLIER)

    def test_no_callback_does_not_raise(self) -> None:
        presenter = ScheduleNavigationPresenter([_system(date(2026, 1, 1))])
        try:
            presenter.apply_ranking(_FEWER)
        except Exception as exc:
            self.fail(f"apply_ranking() raised unexpectedly: {exc}")

    def test_callback_fires_once_per_apply_ranking(self) -> None:
        calls: list[int] = []
        presenter = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1))],
            on_ranking_changed=lambda _s: calls.append(1),
        )
        presenter.apply_ranking(_FEWER)
        presenter.apply_ranking(_EARLIER)
        self.assertEqual(len(calls), 2)


class ApplyRankingSortTests(unittest.TestCase):
    """apply_ranking() sorts the buffer and resets the index."""

    def test_apply_ranking_resets_index_to_position_one(self) -> None:
        s1 = _system(date(2026, 1, 1))
        s2 = _system(date(2026, 1, 2))
        presenter = ScheduleNavigationPresenter([s1, s2])
        presenter.next()
        self.assertEqual(presenter.position(), 2)
        presenter.apply_ranking(_FEWER)
        self.assertEqual(presenter.position(), 1)

    def test_apply_ranking_sorts_by_fewer_days(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 5), date(2026, 2, 10))
        s_few  = _system(date(2026, 3, 1))
        presenter = ScheduleNavigationPresenter([s_many, s_few])
        presenter.apply_ranking(_FEWER)
        self.assertIs(presenter.current_system(), s_few)

    def test_apply_ranking_sorts_by_earlier_start(self) -> None:
        s_late  = _system(date(2026, 3, 15))
        s_early = _system(date(2026, 1, 5))
        presenter = ScheduleNavigationPresenter([s_late, s_early])
        presenter.apply_ranking(_EARLIER)
        self.assertIs(presenter.current_system(), s_early)

    def test_apply_ranking_sorts_by_more_spread(self) -> None:
        s_narrow = _system(date(2026, 1, 1), date(2026, 1, 2))
        s_wide   = _system(date(2026, 1, 1), date(2026, 1, 21))
        presenter = ScheduleNavigationPresenter([s_narrow, s_wide])
        presenter.apply_ranking(_SPREAD)
        self.assertIs(presenter.current_system(), s_wide)

    def test_apply_noop_preserves_order_and_resets_index(self) -> None:
        s1 = _system(date(2026, 5, 1))
        s2 = _system(date(2026, 6, 1))
        presenter = ScheduleNavigationPresenter([s1, s2])
        presenter.next()
        presenter.apply_ranking(_NOOP)
        self.assertIs(presenter.current_system(), s1)
        self.assertEqual(presenter.position(), 1)

    def test_apply_ranking_empty_buffer_does_not_raise(self) -> None:
        presenter = ScheduleNavigationPresenter([])
        try:
            presenter.apply_ranking(_FEWER)
        except Exception as exc:
            self.fail(f"apply_ranking() raised unexpectedly: {exc}")

    def test_apply_ranking_total_is_unchanged(self) -> None:
        systems = [_system(date(2026, i, 1)) for i in range(1, 6)]
        presenter = ScheduleNavigationPresenter(systems)
        presenter.apply_ranking(_FEWER)
        self.assertEqual(presenter.total(), 5)

    def test_sequential_apply_ranking_changes_order_live(self) -> None:
        s_few   = _system(date(2026, 1, 1))                             # 1 day
        s_early = _system(date(2025, 12, 1), date(2025, 12, 10))       # earlier start

        presenter = ScheduleNavigationPresenter([s_few, s_early])

        presenter.apply_ranking(_FEWER)
        self.assertIs(presenter.current_system(), s_few)

        presenter.apply_ranking(_EARLIER)
        self.assertIs(presenter.current_system(), s_early)

    def test_current_ranking_reflects_last_applied_settings(self) -> None:
        presenter = ScheduleNavigationPresenter([_system(date(2026, 1, 1))])
        presenter.apply_ranking(_FEWER)
        self.assertEqual(presenter.current_ranking(), _FEWER)
        presenter.apply_ranking(_EARLIER)
        self.assertEqual(presenter.current_ranking(), _EARLIER)


if __name__ == "__main__":
    unittest.main()
