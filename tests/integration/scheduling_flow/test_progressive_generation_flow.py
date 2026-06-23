from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from application.cache_manager import CacheManager
from constraint_settings import SchedulingConstraintSettings
from models import Course, ExamPeriod, ProgramEnrollment
from ranking_settings import RankingSettings
from scheduling.progressiveGeneration import (
    ProgressiveGenerationOptions,
    ProgressiveResultState,
)
from scheduling.schedulingService import SchedulingService


@pytest.fixture()
def cache_factory(tmp_path: Path, monkeypatch):
    counter = 0

    def make_cache() -> CacheManager:
        nonlocal counter
        counter += 1
        monkeypatch.setattr(CacheManager, "_PKL_PATH", tmp_path / f"cache_{counter}.pkl")
        cache = CacheManager()
        cache.clear()
        cache.set_courses(
            [
                Course(
                    name="Algorithms",
                    course_number="83101",
                    instructor="Dr. Test",
                    programs=[
                        ProgramEnrollment("83101", 1, "FALL", "Obligatory")
                    ],
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
                    end_date=date(2026, 1, 4),
                    excluded_dates=[],
                )
            ]
        )
        cache.set_selected_programs(["83101"])
        cache.set_constraint_settings(SchedulingConstraintSettings.default_configuration())
        cache.set_ranking_settings(RankingSettings([]))
        return cache

    return make_cache


def _scheduled_dates(ranked_schedules) -> list[date]:
    return [
        ranked.exam_system.period_schedules[0].scheduled_exams[0].exam_date
        for ranked in ranked_schedules
    ]


def test_real_service_progressive_generation_emits_partial_batches_and_finalizes_cache(
    cache_factory,
) -> None:
    cache = cache_factory()
    snapshots = []

    final = SchedulingService().run_progressive(
        cache,
        options=ProgressiveGenerationOptions(
            batch_size=1,
            display_limit=10,
            min_update_interval_seconds=0,
        ),
        on_snapshot=snapshots.append,
    )

    partials = [
        snapshot
        for snapshot in snapshots
        if snapshot.state == ProgressiveResultState.PARTIAL
    ]
    assert len(partials) == 4
    assert [snapshot.counters.processed_schedules for snapshot in partials] == [
        1,
        2,
        3,
        4,
    ]
    assert snapshots[-1].state == ProgressiveResultState.COMPLETE
    assert final.state == ProgressiveResultState.COMPLETE
    assert final.counters.generated_schedules == 4
    assert final.counters.displayed_schedules == 4
    assert cache.get_ranked_schedules() == final.ranked_schedules
    assert cache.get_generated_schedules() == [
        ranked.exam_system for ranked in final.ranked_schedules
    ]


def test_progressive_service_preserves_existing_full_ranking_order_when_not_limited(
    cache_factory,
) -> None:
    full_cache = cache_factory()
    progressive_cache = cache_factory()

    full_outcome = SchedulingService().run(full_cache)
    progressive_final = SchedulingService().run_progressive(
        progressive_cache,
        options=ProgressiveGenerationOptions(
            batch_size=1,
            display_limit=10,
            min_update_interval_seconds=0,
        ),
    )

    assert full_outcome.schedule_count == 4
    assert progressive_final.counters.generated_schedules == full_outcome.schedule_count
    assert [ranked.key for ranked in progressive_final.ranked_schedules] == [
        ranked.key for ranked in full_outcome.ranked_schedules
    ]
    assert _scheduled_dates(progressive_final.ranked_schedules) == _scheduled_dates(
        full_outcome.ranked_schedules
    )
