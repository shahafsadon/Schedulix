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


class _CountingGenerator:
    def __init__(self, systems: list[ExamSystem]) -> None:
        self._systems = systems
        self.yielded = 0
        self.generate_calls = 0
        self.diagnostics = _Diagnostics()

    def iter_exam_systems(self, _courses, _exam_periods):
        for system in self._systems:
            self.yielded += 1
            yield system

    def generate_exam_systems(self, _courses, _exam_periods):
        self.generate_calls += 1
        return list(self._systems)


class _DeterministicRankingService:
    def __init__(self, min_gap_by_id: dict[int, int] | None = None) -> None:
        self.min_gap_by_id = min_gap_by_id or {}
        self.batch_calls: list[tuple[list[ExamSystem], int, RankingSettings]] = []
        self.full_calls = 0

    def rank_generated_schedules(self, schedules, ranking_settings):
        self.full_calls += 1
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
        systems = list(schedules)
        self.batch_calls.append((systems, starting_schedule_id, ranking_settings))
        ranked = [
            self._ranked(system, schedule_id)
            for schedule_id, system in enumerate(
                systems,
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
                min_mandatory_gap=self.min_gap_by_id.get(schedule_id, schedule_id),
                average_all_gap=float(schedule_id),
                elective_collision_count=schedule_id,
                mandatory_span=schedule_id,
                max_exams_per_day=schedule_id,
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

        for preference in reversed(ranking_settings.priority_list):
            ranked.sort(
                key=lambda item: getattr(item.metrics, preference.criterion.value),
                reverse=preference.descending,
            )
        return ranked


class _CancellationToken:
    is_cancelled = False


class _ListOnlyGenerator:
    diagnostics = _Diagnostics()

    def generate_exam_systems(self, _courses, _exam_periods):
        raise AssertionError("Progressive generation must not materialize schedules.")


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch) -> CacheManager:
    monkeypatch.setattr(CacheManager, "_PKL_PATH", tmp_path / "cache.pkl")
    cache = CacheManager()
    cache.clear()
    cache.set_courses(
        [
            Course(
                name="Algorithms",
                course_number="83101",
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


def _systems(count: int) -> list[ExamSystem]:
    return [ExamSystem(period_schedules=[]) for _ in range(count)]


def _keys(snapshot) -> list[int]:
    return [ranked.key for ranked in snapshot.ranked_schedules]


def test_normal_generation_stores_all_valid_schedules_without_top_limit(
    isolated_cache: CacheManager,
) -> None:
    generator = _CountingGenerator(_systems(75))
    service = SchedulingService(
        schedule_generator=generator,
        ranking_service=_DeterministicRankingService(),
    )

    outcome = service.run(isolated_cache, rank_results=False)

    assert outcome.schedule_count == 75
    assert len(outcome.schedules) == 75
    assert len(isolated_cache.get_generated_schedules()) == 75
    assert isolated_cache.get_ranked_schedules() == []
    assert isolated_cache.get_result_mode() == "unranked_generated"


def test_progressive_generation_requires_lazy_iterator(
    isolated_cache: CacheManager,
) -> None:
    service = SchedulingService(schedule_generator=_ListOnlyGenerator())

    with pytest.raises(TypeError, match="iter_exam_systems"):
        service.run_progressive(isolated_cache)


def test_progressive_reranks_processed_preview_and_future_batches_after_ranking_change(
    isolated_cache: CacheManager,
) -> None:
    new_settings = RankingSettings(
        [RankingPreference(RankingCriterion.min_mandatory_gap, descending=True)]
    )
    generator = _CountingGenerator(_systems(3))
    service = SchedulingService(
        schedule_generator=generator,
        ranking_service=_DeterministicRankingService(
            min_gap_by_id={1: 1, 2: 10, 3: 5},
        ),
    )
    partial_keys: list[list[int]] = []
    ranking_versions: list[int] = []

    def on_snapshot(snapshot) -> None:
        if snapshot.state != ProgressiveResultState.PARTIAL:
            return
        partial_keys.append(_keys(snapshot))
        ranking_versions.append(snapshot.ranking_version)
        if len(partial_keys) == 1:
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

    assert partial_keys == [[1], [2, 1], [2, 3, 1]]
    assert ranking_versions == [1, 2, 2]
    assert final.state == ProgressiveResultState.COMPLETE
    assert _keys(final) == [2, 3, 1]
    assert generator.generate_calls == 0


def test_progressive_empty_results_emit_clean_complete_snapshot_and_cache_empty_final(
    isolated_cache: CacheManager,
) -> None:
    old_system = ExamSystem(period_schedules=[])
    old_ranked = RankedExamSystem(
        exam_system=old_system,
        metrics=ScheduleMetrics(
            schedule_id=99,
            min_mandatory_gap=99,
            average_all_gap=0,
            elective_collision_count=0,
            mandatory_span=0,
            max_exams_per_day=0,
        ),
        key=99,
    )
    isolated_cache.store_final_schedule_results(
        generated_schedules=[old_system],
        ranked_schedules=[old_ranked],
        ranking_settings=RankingSettings([]),
    )
    snapshots = []

    final = SchedulingService(
        schedule_generator=_CountingGenerator([]),
        ranking_service=_DeterministicRankingService(),
    ).run_progressive(
        isolated_cache,
        options=ProgressiveGenerationOptions(
            batch_size=2,
            display_limit=5,
            min_update_interval_seconds=0,
        ),
        on_snapshot=snapshots.append,
    )

    assert [snapshot.state for snapshot in snapshots] == [
        ProgressiveResultState.COMPLETE,
    ]
    assert final.state == ProgressiveResultState.COMPLETE
    assert final.ranked_schedules == []
    assert final.counters.generated_schedules == 0
    assert final.counters.processed_schedules == 0
    assert final.counters.displayed_schedules == 0
    assert "No valid" in final.message
    assert isolated_cache.get_generated_schedules() == []
    assert isolated_cache.get_ranked_schedules() == []


def test_progressive_large_multi_batch_run_keeps_bounded_preview_and_full_final(
    isolated_cache: CacheManager,
) -> None:
    isolated_cache.set_ranking_settings(
        RankingSettings([RankingPreference(RankingCriterion.min_mandatory_gap)])
    )
    generator = _CountingGenerator(_systems(105))
    snapshots = []

    final = SchedulingService(
        schedule_generator=generator,
        ranking_service=_DeterministicRankingService(),
    ).run_progressive(
        isolated_cache,
        options=ProgressiveGenerationOptions(
            batch_size=17,
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
    assert len(partials) == 7
    assert all(snapshot.counters.displayed_schedules <= 10 for snapshot in partials)
    assert final.state == ProgressiveResultState.COMPLETE
    assert final.counters.generated_schedules == 105
    assert final.counters.accepted_schedules == 105
    assert final.counters.processed_schedules == 105
    assert final.counters.displayed_schedules == 105
    assert _keys(final) == list(range(105, 0, -1))
    assert generator.yielded == 105
    assert len(isolated_cache.get_ranked_schedules()) == 105


def test_progressive_cancellation_after_first_preview_does_not_consume_extra_systems_or_save(
    isolated_cache: CacheManager,
) -> None:
    old_system = ExamSystem(period_schedules=[])
    old_ranked = RankedExamSystem(
        exam_system=old_system,
        metrics=ScheduleMetrics(
            schedule_id=77,
            min_mandatory_gap=77,
            average_all_gap=0,
            elective_collision_count=0,
            mandatory_span=0,
            max_exams_per_day=0,
        ),
        key=77,
    )
    isolated_cache.store_final_schedule_results(
        generated_schedules=[old_system],
        ranked_schedules=[old_ranked],
        ranking_settings=RankingSettings([]),
    )
    generator = _CountingGenerator(_systems(5))
    token = _CancellationToken()
    snapshots = []

    def on_snapshot(snapshot) -> None:
        snapshots.append(snapshot)
        if snapshot.state == ProgressiveResultState.PARTIAL:
            token.is_cancelled = True

    final = SchedulingService(
        schedule_generator=generator,
        ranking_service=_DeterministicRankingService(),
    ).run_progressive(
        isolated_cache,
        options=ProgressiveGenerationOptions(
            batch_size=1,
            display_limit=5,
            min_update_interval_seconds=0,
        ),
        on_snapshot=on_snapshot,
        cancellation_token=token,
    )

    assert [snapshot.state for snapshot in snapshots] == [
        ProgressiveResultState.PARTIAL,
        ProgressiveResultState.CANCELLED,
    ]
    assert final.state == ProgressiveResultState.CANCELLED
    assert generator.yielded == 1
    assert generator.generate_calls == 0
    assert isolated_cache.get_generated_schedules() == [old_system]
    assert isolated_cache.get_ranked_schedules() == [old_ranked]
