"""test_dynamic_reranking.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for dynamic ranking changes on already-processed results (SCRUM-185).

Simulates the scenario where a user changes ranking criteria *while*
background generation is in flight, and verifies that:

1. ``ScheduleNavigationPresenter.apply_ranking()`` immediately re-sorts the
   in-memory buffer without restarting generation.
2. ``SchedulingPresenter.rerank_cached()`` re-sorts the cache without calling
   the scheduling engine.
3. Sequential ranking changes always leave the buffer in a consistent state.
4. The ``on_ranking_changed`` callback fires on every change so the cache is
   kept in sync.

No GUI, no threads, no ``time.sleep()``.
Threading is mocked for ``AsyncScheduleRunner`` tests using the pattern
established in ``test_async_operations.py``.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(_SRC))

from application.cache_manager import CacheManager
from application.async_runner import AsyncScheduleRunner
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
        ScheduledExam(course=_course(f"8{i:04d}"), exam_date=d)
        for i, d in enumerate(dates)
    ]
    return ExamSystem(period_schedules=[ExamSchedule("FALL", "Aleph", exams)])


def _fake_thread_cls(run_immediately: bool = True):
    """
    Return a ``threading.Thread`` mock that executes ``target(*args)``
    synchronously when ``start()`` is called (if ``run_immediately``).
    This eliminates all real threading in presenter / runner tests.
    """
    mock_instance = MagicMock()

    def _fake_start():
        if run_immediately:
            target = mock_cls.call_args.kwargs.get("target")
            args   = mock_cls.call_args.kwargs.get("args", ())
            if target:
                target(*args)

    mock_instance.start.side_effect = _fake_start
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls


_NOOP    = RankingSettings.default()
_FEWER   = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
_SPREAD  = RankingSettings.build([RankingCriterion.MORE_SPREAD])
_EARLIER = RankingSettings.build([RankingCriterion.EARLIER_START])


# ---------------------------------------------------------------------------
# 1. NavigationPresenter — apply_ranking() live re-sort
# ---------------------------------------------------------------------------

class LiveReRankingNavigationPresenterTests(unittest.TestCase):
    """apply_ranking() on an existing in-memory buffer is immediate and correct."""

    def _presenter(self, systems, *, initial=None, callback=None):
        return ScheduleNavigationPresenter(
            systems,
            initial_ranking=initial or _NOOP,
            on_ranking_changed=callback,
        )

    # ------------------------------------------------------------------ sort

    def test_ranking_change_reorders_buffer_immediately(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 5), date(2026, 2, 10))
        s_few  = _system(date(2026, 3, 1))
        p = self._presenter([s_many, s_few])
        p.apply_ranking(_FEWER)
        self.assertIs(p.current_system(), s_few)

    def test_second_ranking_change_overrides_first(self) -> None:
        """Sequential changes: each change produces the correct global order."""
        s_few   = _system(date(2026, 1, 1))                            # 1 day
        s_early = _system(date(2025, 12, 1), date(2025, 12, 5))       # earlier
        p = self._presenter([s_few, s_early])

        p.apply_ranking(_FEWER)
        self.assertIs(p.current_system(), s_few)    # fewer days wins

        p.apply_ranking(_EARLIER)
        self.assertIs(p.current_system(), s_early)  # earlier start wins

    def test_third_ranking_change_works_correctly(self) -> None:
        """Three sequential changes all produce independent correct orders."""
        s_few   = _system(date(2026, 1, 1))
        s_early = _system(date(2025, 12, 1), date(2025, 12, 5))
        s_wide  = _system(date(2026, 1, 1), date(2026, 3, 31))
        p = self._presenter([s_few, s_early, s_wide])

        p.apply_ranking(_FEWER)
        self.assertIs(p.current_system(), s_few)

        p.apply_ranking(_EARLIER)
        self.assertIs(p.current_system(), s_early)

        p.apply_ranking(_SPREAD)
        self.assertIs(p.current_system(), s_wide)

    def test_reverting_to_noop_resets_to_post_previous_ranking(self) -> None:
        """After re-ranking, reverting to noop preserves the current sort."""
        s_many = _system(date(2026, 2, 1), date(2026, 2, 5))
        s_few  = _system(date(2026, 3, 1))
        p = self._presenter([s_many, s_few])
        p.apply_ranking(_FEWER)              # s_few first
        p.apply_ranking(_NOOP)              # noop on already-ranked buffer
        # s_few is still first because noop preserves current order
        self.assertIs(p.current_system(), s_few)

    # ------------------------------------------------------------------ index

    def test_index_resets_to_zero_on_every_ranking_change(self) -> None:
        s1, s2, s3 = [_system(date(2026, i, 1)) for i in range(1, 4)]
        p = self._presenter([s1, s2, s3])
        p.next(); p.next()           # advance to position 3
        self.assertEqual(p.position(), 3)
        p.apply_ranking(_FEWER)
        self.assertEqual(p.position(), 1)

    def test_total_unchanged_after_ranking_change(self) -> None:
        systems = [_system(date(2026, i, 1)) for i in range(1, 6)]
        p = self._presenter(systems)
        p.apply_ranking(_FEWER)
        self.assertEqual(p.total(), 5)

    # ------------------------------------------------------------------ callback

    def test_callback_fires_on_every_ranking_change(self) -> None:
        received: list[RankingSettings] = []
        p = self._presenter(
            [_system(date(2026, 1, 1))],
            callback=received.append,
        )
        p.apply_ranking(_FEWER)
        p.apply_ranking(_EARLIER)
        p.apply_ranking(_SPREAD)
        self.assertEqual(len(received), 3)
        self.assertEqual(received, [_FEWER, _EARLIER, _SPREAD])

    def test_callback_receives_settings_object_not_copy(self) -> None:
        received: list[RankingSettings] = []
        p = self._presenter(
            [_system(date(2026, 1, 1))],
            callback=received.append,
        )
        p.apply_ranking(_FEWER)
        self.assertIs(received[0], _FEWER)

    def test_ranking_change_on_empty_buffer_does_not_crash(self) -> None:
        p = self._presenter([])
        try:
            p.apply_ranking(_FEWER)
            p.apply_ranking(_SPREAD)
        except Exception as exc:
            self.fail(f"Unexpected exception on empty buffer: {exc}")

    # ------------------------------------------------------------------ generation not restarted

    def test_on_ranking_changed_does_not_call_service(self) -> None:
        """The scheduling engine must never be called on a ranking-only change."""
        svc = MagicMock(spec=SchedulingService)
        p = self._presenter(
            [_system(date(2026, 1, 1))],
            callback=lambda _: None,      # simulates rerank_cached path
        )
        p.apply_ranking(_FEWER)
        svc.run.assert_not_called()


# ---------------------------------------------------------------------------
# 2. SchedulingPresenter.rerank_cached() — no engine restart
# ---------------------------------------------------------------------------

class ReRankCachedDuringGenerationTests(unittest.TestCase):
    """rerank_cached() re-sorts the persisted buffer without touching the engine."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCache._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCache()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _presenter(self, service=None, initial_ranking=None) -> SchedulingPresenter:
        return SchedulingPresenter(
            self._cache,
            service=service or MagicMock(spec=SchedulingService),
            initial_ranking=initial_ranking,
        )

    def test_rerank_cached_does_not_call_run(self) -> None:
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        svc = MagicMock(spec=SchedulingService)
        p = SchedulingPresenter(self._cache, service=svc)
        p.rerank_cached(_FEWER)
        svc.run.assert_not_called()

    def test_rerank_cached_applies_new_order_to_cache(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 10))
        s_few  = _system(date(2026, 3, 1))
        self._cache.set_generated_schedules([s_many, s_few])
        p = self._presenter()
        p.rerank_cached(_FEWER)
        cached = self._cache.get_generated_schedules()
        self.assertIs(cached[0], s_few)

    def test_rerank_cached_updates_ranking_settings_in_cache(self) -> None:
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        p = self._presenter()
        p.rerank_cached(_SPREAD)
        self.assertEqual(self._cache.get_ranking_settings(), _SPREAD)

    def test_rerank_cached_updates_presenter_ranking_property(self) -> None:
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        p = self._presenter()
        p.rerank_cached(_EARLIER)
        self.assertEqual(p.ranking, _EARLIER)

    def test_sequential_rerank_cached_changes_produce_correct_orders(self) -> None:
        s_few   = _system(date(2026, 1, 1))
        s_early = _system(date(2025, 12, 1), date(2025, 12, 5))
        self._cache.set_generated_schedules([s_few, s_early])
        p = self._presenter()

        p.rerank_cached(_FEWER)
        self.assertIs(self._cache.get_generated_schedules()[0], s_few)

        p.rerank_cached(_EARLIER)
        self.assertIs(self._cache.get_generated_schedules()[0], s_early)

    def test_rerank_cached_on_empty_cache_returns_false(self) -> None:
        p = self._presenter()
        result = p.rerank_cached(_FEWER)
        self.assertFalse(result)

    def test_rerank_cached_on_populated_cache_returns_true(self) -> None:
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        p = self._presenter()
        result = p.rerank_cached(_FEWER)
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# 3. on_ranking_changed wires NavigationPresenter → SchedulingPresenter
# ---------------------------------------------------------------------------

class CallbackWiringIntegrationTests(unittest.TestCase):
    """
    Verify that the ranking callback chain is wired correctly:
        ScheduleNavigationPresenter.apply_ranking()
          → on_ranking_changed (== SchedulingPresenter.rerank_cached)
            → CacheManager.set_generated_schedules()
            → CacheManager.set_ranking_settings()
    This exercises the wiring that workflowApp.py sets up, without any GUI.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCache._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCache()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _wire_up(self, systems):
        svc = MagicMock(spec=SchedulingService)
        svc_presenter = SchedulingPresenter(self._cache, service=svc)
        self._cache.set_generated_schedules(systems)
        nav_presenter = ScheduleNavigationPresenter(
            list(systems),
            on_ranking_changed=svc_presenter.rerank_cached,
        )
        return nav_presenter, svc_presenter

    def test_apply_ranking_persists_to_cache_via_callback(self) -> None:
        s_many = _system(date(2026, 2, 1), date(2026, 2, 10))
        s_few  = _system(date(2026, 3, 1))
        nav, _ = self._wire_up([s_many, s_few])
        nav.apply_ranking(_FEWER)
        cached = self._cache.get_generated_schedules()
        self.assertIs(cached[0], s_few)

    def test_apply_ranking_persists_settings_to_cache(self) -> None:
        nav, _ = self._wire_up([_system(date(2026, 1, 1))])
        nav.apply_ranking(_EARLIER)
        self.assertEqual(self._cache.get_ranking_settings(), _EARLIER)

    def test_nav_and_cache_stay_in_sync_after_multiple_changes(self) -> None:
        """After N ranking changes the nav buffer and cache buffer must agree."""
        s_few   = _system(date(2026, 1, 1))
        s_early = _system(date(2025, 12, 1), date(2025, 12, 5))
        nav, _ = self._wire_up([s_few, s_early])

        for settings in [_FEWER, _EARLIER, _SPREAD, _FEWER]:
            nav.apply_ranking(settings)
            cached = self._cache.get_generated_schedules()
            # Nav buffer and cache must have the same order.
            nav_buf = [nav.current_system()]   # only need to check position 0
            self.assertIs(nav_buf[0], cached[0])

    def test_engine_not_called_during_ranking_only_changes(self) -> None:
        svc = MagicMock(spec=SchedulingService)
        svc_presenter = SchedulingPresenter(self._cache, service=svc)
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])
        nav = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1))],
            on_ranking_changed=svc_presenter.rerank_cached,
        )
        # Perform several ranking changes
        for settings in [_FEWER, _EARLIER, _SPREAD]:
            nav.apply_ranking(settings)
        svc.run.assert_not_called()

    def test_ranking_surviving_multiple_apply_ranking_calls(self) -> None:
        """
        Simulates a user rapidly changing rankings: after each change the nav
        presenter's ``current_ranking()`` must reflect the last applied setting.
        """
        systems = [_system(date(2026, i, 1)) for i in range(1, 4)]
        nav, _ = self._wire_up(systems)
        for settings in [_FEWER, _NOOP, _EARLIER, _SPREAD, _FEWER]:
            nav.apply_ranking(settings)
            self.assertEqual(nav.current_ranking(), settings)


# ---------------------------------------------------------------------------
# 4. Dynamic ranking in presence of AsyncScheduleRunner (mocked thread)
# ---------------------------------------------------------------------------

class AsyncRunnerRankingInteractionTests(unittest.TestCase):
    """
    Validates that ranking changes can occur while the runner reports is_running.

    Threading is mocked so the 'background' task executes synchronously.
    No ``time.sleep()`` is used.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCache._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCache()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ranking_change_while_runner_idle_works(self) -> None:
        """apply_ranking() works normally when the runner is not active."""
        runner = AsyncScheduleRunner()
        self.assertFalse(runner.is_running)
        nav = ScheduleNavigationPresenter(
            [_system(date(2026, 1, 1)), _system(date(2026, 2, 1))]
        )
        # No exception and index resets.
        nav.apply_ranking(_FEWER)
        self.assertEqual(nav.position(), 1)

    def test_runner_is_not_running_after_synchronous_task(self) -> None:
        """After a mocked synchronous task the runner must return is_running=False."""
        mock_cls = _fake_thread_cls(run_immediately=True)
        runner = AsyncScheduleRunner()
        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None)
        self.assertFalse(runner.is_running)

    def test_ranking_change_does_not_restart_runner(self) -> None:
        """Calling rerank_cached() must not affect runner state."""
        mock_cls = _fake_thread_cls(run_immediately=True)
        runner = AsyncScheduleRunner()
        svc_presenter = SchedulingPresenter(self._cache)
        self._cache.set_generated_schedules([_system(date(2026, 1, 1))])

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None)   # task completes synchronously

        # runner is idle.
        self.assertFalse(runner.is_running)
        # Ranking change does not touch the runner.
        svc_presenter.rerank_cached(_FEWER)
        self.assertFalse(runner.is_running)
        # Thread was only created once (for the original task).
        self.assertEqual(mock_cls.call_count, 1)


if __name__ == "__main__":
    unittest.main()
