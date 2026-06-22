import sys
import tempfile
from datetime import date
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from models import Course, ExamPeriod, ProgramEnrollment
from ranking_settings import RankingSettings, RankingPreference, RankingCriterion
from scheduling.schedulingService import SchedulingService
from scheduling.progressiveGeneration import (
    ProgressiveGenerationOptions,
    ProgressiveResultState,
    ProgressiveRankedSnapshot,
)
from application.async_runner import CancellationToken
from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter


def exam_course(name, number, program, semester="FALL", status="Obligatory"):
    return Course(
        name=name,
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment(program, 1, semester, status)],
        evaluation_type="Exam",
    )


def fall_period(end_day=2):
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, end_day),
        excluded_dates=[],
    )


class MockClock:
    def __init__(self, start_time: float = 0.0, auto_advance: float = 0.0):
        self._time = start_time
        self._auto_advance = auto_advance
    
    def __call__(self) -> float:
        current = self._time
        self._time += self._auto_advance
        return current
        
    def advance(self, seconds: float) -> None:
        self._time += seconds


class ProgressiveGenerationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_pkl_path = CacheManager._PKL_PATH
        self._tmp = tempfile.TemporaryDirectory()
        CacheManager._PKL_PATH = Path(self._tmp.name) / "test_cache.pkl"
        
        self.cache = CacheManager()
        self.cache.clear()
        
        self.service = SchedulingService()
        self.clock = MockClock(auto_advance=1.0)
        self.service._clock = self.clock

    def tearDown(self) -> None:
        CacheManager._PKL_PATH = self._original_pkl_path
        self._tmp.cleanup()

    def test_run_progressive_empty_scenario(self) -> None:
        # Valid setup but no courses match selected programs -> 0 schedules
        self.cache.set_courses([exam_course("Out", "83200", "83108")])
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])
        
        snapshots = []
        options = ProgressiveGenerationOptions(batch_size=2)
        
        final_snapshot = self.service.run_progressive(
            cache=self.cache,
            options=options,
            on_snapshot=snapshots.append,
        )
        
        self.assertEqual(final_snapshot.state, ProgressiveResultState.COMPLETE)
        self.assertEqual(final_snapshot.relevant_course_count, 0)
        self.assertEqual(final_snapshot.ranked_schedules, [])

    def test_run_progressive_small_scenario(self) -> None:
        self.cache.set_courses([
            exam_course("Physics 1", "83102", "83101"),
        ])
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])
        
        snapshots = []
        options = ProgressiveGenerationOptions(batch_size=10)
        
        final_snapshot = self.service.run_progressive(
            cache=self.cache,
            options=options,
            on_snapshot=snapshots.append,
        )
        
        self.assertEqual(final_snapshot.state, ProgressiveResultState.COMPLETE)
        self.assertGreater(len(final_snapshot.ranked_schedules), 0)

    def test_run_progressive_large_scenario_with_cancellation(self) -> None:
        # Will generate many systems
        self.cache.set_courses([
            exam_course("C1", "1", "83101"),
            exam_course("C2", "2", "83101"),
            exam_course("C3", "3", "83101"),
            exam_course("C4", "4", "83101"),
        ])
        self.cache.set_exam_periods([fall_period(end_day=5)])
        self.cache.set_selected_programs(["83101"])

        token = CancellationToken()
        snapshots = []
        
        def on_snapshot(snapshot: ProgressiveRankedSnapshot) -> None:
            snapshots.append(snapshot)
            if snapshot.state == ProgressiveResultState.PARTIAL:
                token.cancel()
            
        options = ProgressiveGenerationOptions(
            batch_size=1,
            min_update_interval_seconds=0.5,
            cache_final_preview=True
        )
        
        final_snapshot = self.service.run_progressive(
            cache=self.cache,
            options=options,
            on_snapshot=on_snapshot,
            cancellation_token=token,
        )
        
        self.assertEqual(final_snapshot.state, ProgressiveResultState.CANCELLED)
        # Verify in-memory previews did not poison cache
        self.assertEqual(self.cache.get_generated_schedules(), [])
        
    def test_scrum_183_dynamic_ranking_during_generation(self) -> None:
        """Verify behavior when ranking changes occur during active generation."""
        self.cache.set_courses([
            exam_course("C1", "1", "83101"),
            exam_course("C2", "2", "83101"),
            exam_course("C3", "3", "83101"),
        ])
        self.cache.set_exam_periods([fall_period(end_day=3)])
        self.cache.set_selected_programs(["83101"])

        presenter = ScheduleNavigationPresenter([])
        snapshots = []
        
        def on_snapshot(snapshot: ProgressiveRankedSnapshot) -> None:
            snapshots.append(snapshot)
            presenter.update_schedules(
                snapshot.ranked_schedules,
                is_partial=(snapshot.state == ProgressiveResultState.PARTIAL),
                systems_seen=0,
                displayed_count=len(snapshot.ranked_schedules),
            )
            
            # Simulate a user applying a new ranking while generation is active
            if len(snapshots) == 1:
                new_ranking = RankingSettings([
                    RankingPreference(RankingCriterion.min_mandatory_gap, descending=False)
                ])
                presenter.apply_ranking(new_ranking)
            
        options = ProgressiveGenerationOptions(
            batch_size=2,
            min_update_interval_seconds=0.5,
        )
        
        final_snapshot = self.service.run_progressive(
            cache=self.cache,
            options=options,
            on_snapshot=on_snapshot,
        )
        
        # After completion
        presenter.update_schedules(
            final_snapshot.ranked_schedules,
            is_partial=False,
            systems_seen=0,
            displayed_count=len(final_snapshot.ranked_schedules),
        )
        
        self.assertTrue(presenter._active_ranking.priority_list)
        self.assertEqual(
            presenter._active_ranking.priority_list[0].criterion,
            RankingCriterion.min_mandatory_gap,
        )
        
        if presenter.total() > 1:
            first_sys = presenter._ranked_schedules[0]
            last_sys = presenter._ranked_schedules[-1]
            self.assertLessEqual(
                first_sys.metrics.min_mandatory_gap,
                last_sys.metrics.min_mandatory_gap
            )

if __name__ == "__main__":
    unittest.main()
