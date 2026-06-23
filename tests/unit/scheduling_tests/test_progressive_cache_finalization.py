from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from application.cache_manager import CacheManager
from constraint_settings import SchedulingConstraintSettings
from models import Course, ExamPeriod, ProgramEnrollment
from ranking_settings import (
    RankedExamSystem,
    RankingCriterion,
    RankingPreference,
    RankingSettings,
    ScheduleMetrics,
)
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.progressiveGeneration import (
    ProgressiveGenerationOptions,
    ProgressiveResultState,
)
from scheduling.schedulingService import SchedulingService


class _Diagnostics:
    generated_candidates = 0
    accepted_candidates = 0
    pruned_candidates = 0


class _FakeProgressiveGenerator:
    def __init__(self, systems: list[ExamSystem]) -> None:
        self._systems = systems
        self.diagnostics = _Diagnostics()

    def iter_exam_systems(self, _courses, _exam_periods):
        yield from self._systems


class _DeterministicRankingService:
    """Rank batches with deterministic metrics that make reordering visible."""

    _min_gap_by_schedule_id = {
        1: 1,
        2: 10,
        3: 5,
    }

    def rank_generated_schedules(self, schedules, ranking_settings):
        ranked = [
            self._ranked(system, schedule_id)
            for schedule_id, system in enumerate(schedules, start=1)
        ]
        return type(
            "Outcome",
            (),
            {
                "ranked_schedules": self._rank(ranked, ranking_settings),
                "elapsed_seconds": 0.0,
            },
        )()

    def rank_generated_batch(self, schedules, ranking_settings, starting_schedule_id):
        ranked = [
            self._ranked(system, schedule_id)
            for schedule_id, system in enumerate(
                schedules,
                start=starting_schedule_id,
            )
        ]
        return type(
            "Outcome",
            (),
            {
                "ranked_schedules": self._rank(ranked, ranking_settings),
                "elapsed_seconds": 0.0,
            },
        )()

    def rerank(self, ranked_schedules, ranking_settings):
        return type(
            "Outcome",
            (),
            {
                "ranked_schedules": self._rank(ranked_schedules, ranking_settings),
                "elapsed_seconds": 0.0,
            },
        )()

    def _ranked(self, system: ExamSystem, schedule_id: int) -> RankedExamSystem:
        return RankedExamSystem(
            exam_system=system,
            metrics=ScheduleMetrics(
                schedule_id=schedule_id,
                min_mandatory_gap=self._min_gap_by_schedule_id[schedule_id],
                average_all_gap=0,
                elective_collision_count=0,
                mandatory_span=0,
                max_exams_per_day=0,
            ),
            key=schedule_id,
        )

    @staticmethod
    def _rank(
        ranked_schedules: list[RankedExamSystem],
        ranking_settings: RankingSettings,
    ) -> list[RankedExamSystem]:
        ranked = list(ranked_schedules)
        if not ranking_settings.priority_list:
            return sorted(ranked, key=lambda item: item.key)
        return sorted(ranked, key=lambda item: item.metrics.min_mandatory_gap, reverse=True)


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch) -> CacheManager:
    monkeypatch.setattr(CacheManager, "_PKL_PATH", tmp_path / "cache.pkl")
    cache = CacheManager()
    cache.clear()
    cache.set_courses(
        [
            Course(
                name="Physics",
                course_number="83102",
                instructor="Dr. Test",
                programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
                evaluation_type="Exam",
            )
        ]
    )
    cache.set_exam_periods(
        [
            ExamPeriod(
                semester="FALL",
                moed="Aleph",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 3),
                excluded_dates=[],
            )
        ]
    )
    cache.set_selected_programs(["83101"])
    cache.set_constraint_settings(SchedulingConstraintSettings.default_configuration())
    cache.set_ranking_settings(RankingSettings([]))
    return cache


def _ranked(system: ExamSystem, key: int) -> RankedExamSystem:
    return RankedExamSystem(
        exam_system=system,
        metrics=ScheduleMetrics(
            schedule_id=key,
            min_mandatory_gap=key,
            average_all_gap=0,
            elective_collision_count=0,
            mandatory_span=0,
            max_exams_per_day=0,
        ),
        key=key,
    )


def test_progressive_partial_snapshots_are_session_only_and_final_cache_is_atomic(
    isolated_cache: CacheManager,
) -> None:
    old_system = ExamSystem(period_schedules=[])
    old_ranked = _ranked(old_system, 99)
    isolated_cache.store_final_schedule_results(
        generated_schedules=[old_system],
        ranked_schedules=[old_ranked],
        ranking_settings=RankingSettings([]),
    )

    new_systems = [ExamSystem(period_schedules=[]), ExamSystem(period_schedules=[])]
    service = SchedulingService(
        schedule_generator=_FakeProgressiveGenerator(new_systems),
    )
    partial_seen = False

    def on_snapshot(snapshot) -> None:
        nonlocal partial_seen
        if snapshot.state == ProgressiveResultState.PARTIAL:
            partial_seen = True
            assert isolated_cache.get_generated_schedules() == [old_system]
            assert isolated_cache.get_ranked_schedules() == [old_ranked]

    final = service.run_progressive(
        isolated_cache,
        options=ProgressiveGenerationOptions(
            batch_size=1,
            display_limit=2,
            min_update_interval_seconds=0,
        ),
        on_snapshot=on_snapshot,
    )

    assert partial_seen
    assert final.state == ProgressiveResultState.COMPLETE
    assert isolated_cache.get_ranked_schedules() == final.ranked_schedules
    assert isolated_cache.get_generated_schedules() == [old_system]


def test_progressive_finalization_uses_ranking_settings_changed_during_generation(
    isolated_cache: CacheManager,
) -> None:
    new_settings = RankingSettings(
        [RankingPreference(RankingCriterion.min_mandatory_gap)]
    )
    service = SchedulingService(
        schedule_generator=_FakeProgressiveGenerator(
            [
                ExamSystem(period_schedules=[]),
                ExamSystem(period_schedules=[]),
                ExamSystem(period_schedules=[]),
            ]
        ),
        ranking_service=_DeterministicRankingService(),
    )
    changed_settings = False

    def on_snapshot(snapshot) -> None:
        nonlocal changed_settings
        if snapshot.state == ProgressiveResultState.PARTIAL and not changed_settings:
            changed_settings = True
            isolated_cache.set_ranking_settings(new_settings)

    final = service.run_progressive(
        isolated_cache,
        options=ProgressiveGenerationOptions(
            batch_size=1,
            display_limit=3,
            min_update_interval_seconds=0,
        ),
        on_snapshot=on_snapshot,
    )

    assert changed_settings
    assert isolated_cache.get_ranking_settings() == new_settings
    assert [ranked.key for ranked in final.ranked_schedules] == [2, 3, 1]
    assert isolated_cache.get_ranked_schedules() == final.ranked_schedules
