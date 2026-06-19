"""Unit tests for SchedulingPresenter SCRUM-184 additions.

Covers:
- generate() writes only COMPLETE snapshots to cache.
- generate() applies the active ranking before persisting.
- generate() stores ranking_settings in cache alongside schedules.
- rerank_cached() re-sorts without calling the scheduling engine.
- rerank_cached() returns False on empty cache, True when schedules exist.
- rerank_cached() writes new ranking_settings to cache.
- invalidate_for_threshold_change() clears schedules and resets ranking.
- initial_ranking parameter is respected on first generate() call.
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from gui.presenters.schedulingPresenter import GenerationResult, SchedulingPresenter
from models import Course, ProgramEnrollment
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.rankingSettings import RankingCriterion, RankingSettings
from scheduling.schedulingService import SchedulingOutcome, SchedulingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _TmpCacheManager(CacheManager):
    pass


def _make_course(number: str) -> Course:
    return Course(
        name=f"Course {number}",
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def _make_system(*exam_dates: date) -> ExamSystem:
    exams = [
        ScheduledExam(course=_make_course(f"9{i:04d}"), exam_date=d)
        for i, d in enumerate(exam_dates)
    ]
    return ExamSystem(
        period_schedules=[ExamSchedule("FALL", "Aleph", exams)]
    )


def _fake_service(systems: list[ExamSystem], relevant: int = 3) -> SchedulingService:
    """Return a SchedulingService fake that produces *systems* on every run()."""
    svc = MagicMock(spec=SchedulingService)
    svc.run.return_value = SchedulingOutcome(
        relevant_course_count=relevant,
        schedule_count=len(systems),
        schedules=systems,
    )
    return svc


class GenerateTests(unittest.TestCase):
    """SchedulingPresenter.generate() enforces COMPLETE-only cache writes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCacheManager._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCacheManager()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_generate_stores_schedules_in_cache(self) -> None:
        systems = [_make_system(date(2026, 1, 1))]
        presenter = SchedulingPresenter(self._cache, service=_fake_service(systems))
        result = presenter.generate()
        self.assertTrue(result.success)
        self.assertEqual(self._cache.get_generated_schedules(), systems)

    def test_generate_stores_ranking_settings_in_cache(self) -> None:
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        systems = [_make_system(date(2026, 1, 1))]
        presenter = SchedulingPresenter(
            self._cache,
            service=_fake_service(systems),
            initial_ranking=settings,
        )
        presenter.generate()
        self.assertEqual(self._cache.get_ranking_settings(), settings)

    def test_generate_applies_ranking_before_persisting(self) -> None:
        """Fewer-days criterion: s_few (1 day) must be persisted first."""
        s_many = _make_system(date(2026, 2, 1), date(2026, 2, 10))
        s_few  = _make_system(date(2026, 3, 1))
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        presenter = SchedulingPresenter(
            self._cache,
            service=_fake_service([s_many, s_few]),
            initial_ranking=settings,
        )
        presenter.generate()
        cached = self._cache.get_generated_schedules()
        self.assertIs(cached[0], s_few)

    def test_generate_zero_schedules_does_not_persist_empty_list(self) -> None:
        """A zero-result run should NOT overwrite a previously cached list."""
        # Pre-populate cache with one system.
        existing = _make_system(date(2026, 1, 1))
        self._cache.set_generated_schedules([existing])

        svc = MagicMock(spec=SchedulingService)
        svc.run.return_value = SchedulingOutcome(
            relevant_course_count=3,
            schedule_count=0,
            schedules=[],
        )
        presenter = SchedulingPresenter(self._cache, service=svc)
        result = presenter.generate()
        self.assertTrue(result.success)
        self.assertEqual(result.schedule_count, 0)
        # Cache must still hold the pre-existing system.
        self.assertEqual(len(self._cache.get_generated_schedules()), 1)

    def test_generate_value_error_returns_failure_result(self) -> None:
        svc = MagicMock(spec=SchedulingService)
        svc.run.side_effect = ValueError("No courses loaded.")
        presenter = SchedulingPresenter(self._cache, service=svc)
        result = presenter.generate()
        self.assertFalse(result.success)
        self.assertIn("No courses", result.message)

    def test_generate_returns_generation_result_dataclass(self) -> None:
        systems = [_make_system(date(2026, 1, 5)), _make_system(date(2026, 1, 8))]
        presenter = SchedulingPresenter(self._cache, service=_fake_service(systems))
        result = presenter.generate()
        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.schedule_count, 2)


class RerankCachedTests(unittest.TestCase):
    """SchedulingPresenter.rerank_cached() — fast path without regeneration."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCacheManager._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCacheManager()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_presenter(self, service=None) -> SchedulingPresenter:
        return SchedulingPresenter(
            self._cache,
            service=service or MagicMock(spec=SchedulingService),
        )

    def test_rerank_returns_false_on_empty_cache(self) -> None:
        presenter = self._make_presenter()
        result = presenter.rerank_cached(
            RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        )
        self.assertFalse(result)

    def test_rerank_returns_true_when_schedules_cached(self) -> None:
        self._cache.set_generated_schedules([_make_system(date(2026, 1, 1))])
        presenter = self._make_presenter()
        result = presenter.rerank_cached(
            RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        )
        self.assertTrue(result)

    def test_rerank_does_not_call_scheduling_engine(self) -> None:
        """The scheduling service must never be invoked on a ranking-only change."""
        self._cache.set_generated_schedules([_make_system(date(2026, 1, 1))])
        svc = MagicMock(spec=SchedulingService)
        presenter = SchedulingPresenter(self._cache, service=svc)
        presenter.rerank_cached(
            RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        )
        svc.run.assert_not_called()

    def test_rerank_sorts_cached_schedules(self) -> None:
        s_many = _make_system(date(2026, 2, 1), date(2026, 2, 10))
        s_few  = _make_system(date(2026, 3, 1))
        self._cache.set_generated_schedules([s_many, s_few])
        presenter = self._make_presenter()
        presenter.rerank_cached(RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS]))
        cached = self._cache.get_generated_schedules()
        self.assertIs(cached[0], s_few)

    def test_rerank_updates_ranking_settings_in_cache(self) -> None:
        self._cache.set_generated_schedules([_make_system(date(2026, 1, 1))])
        settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        presenter = self._make_presenter()
        presenter.rerank_cached(settings)
        self.assertEqual(self._cache.get_ranking_settings(), settings)

    def test_rerank_updates_presenter_ranking_property(self) -> None:
        self._cache.set_generated_schedules([_make_system(date(2026, 1, 1))])
        settings = RankingSettings.build([RankingCriterion.EARLIER_START])
        presenter = self._make_presenter()
        presenter.rerank_cached(settings)
        self.assertEqual(presenter.ranking, settings)

    def test_rerank_noop_settings_preserves_order(self) -> None:
        s1 = _make_system(date(2026, 1, 1))
        s2 = _make_system(date(2026, 2, 1))
        self._cache.set_generated_schedules([s1, s2])
        presenter = self._make_presenter()
        presenter.rerank_cached(RankingSettings.default())
        cached = self._cache.get_generated_schedules()
        self.assertIs(cached[0], s1)


class InvalidateThresholdTests(unittest.TestCase):
    """SchedulingPresenter.invalidate_for_threshold_change()."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        _TmpCacheManager._PKL_PATH = Path(self._tmp.name) / "test.pkl"
        self._cache = _TmpCacheManager()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_invalidate_clears_cached_schedules(self) -> None:
        self._cache.set_generated_schedules([_make_system(date(2026, 1, 1))])
        presenter = SchedulingPresenter(self._cache)
        presenter.invalidate_for_threshold_change()
        self.assertEqual(self._cache.get_generated_schedules(), [])

    def test_invalidate_resets_cached_ranking(self) -> None:
        settings = RankingSettings.build([RankingCriterion.FEWER_EXAM_DAYS])
        self._cache.set_ranking_settings(settings)
        presenter = SchedulingPresenter(self._cache)
        presenter.invalidate_for_threshold_change()
        self.assertTrue(self._cache.get_ranking_settings().is_noop())

    def test_invalidate_resets_presenter_ranking_property(self) -> None:
        settings = RankingSettings.build([RankingCriterion.MORE_SPREAD])
        presenter = SchedulingPresenter(
            self._cache, initial_ranking=settings
        )
        presenter.invalidate_for_threshold_change()
        self.assertTrue(presenter.ranking.is_noop())


if __name__ == "__main__":
    unittest.main()
