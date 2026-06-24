from __future__ import annotations

import pytest

from ranking_settings import (
    MISSING_METRIC_VALUE,
    RankedExamSystem,
    RankingCriterion,
    RankingPreference,
    RankingSettings,
    ScheduleMetrics,
)
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.rankedResultsBuffer import RankedResultsBuffer


def _ranked(
    key: int,
    *,
    min_mandatory_gap: int = 0,
    average_all_gap: float = 0,
    elective_collision_count: int = 0,
    mandatory_span: int = 0,
    max_exams_per_day: int = 0,
) -> RankedExamSystem:
    return RankedExamSystem(
        exam_system=ExamSystem(period_schedules=[]),
        metrics=ScheduleMetrics(
            schedule_id=key,
            min_mandatory_gap=min_mandatory_gap,
            average_all_gap=average_all_gap,
            elective_collision_count=elective_collision_count,
            mandatory_span=mandatory_span,
            max_exams_per_day=max_exams_per_day,
        ),
        key=key,
    )


def _keys(ranked_schedules: list[RankedExamSystem]) -> list[int]:
    return [ranked.key for ranked in ranked_schedules]


def test_buffer_returns_schedules_ordered_by_active_ranking_settings() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        ),
        preview_limit=3,
    )

    preview = buffer.add_ranked_batch(
        [
            _ranked(1, min_mandatory_gap=2),
            _ranked(2, min_mandatory_gap=7),
            _ranked(3, min_mandatory_gap=4),
        ]
    )

    assert _keys(preview) == [2, 3, 1]
    assert _keys(buffer.current_preview()) == [2, 3, 1]


def test_new_batches_are_merged_without_losing_existing_better_results() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        ),
        preview_limit=2,
    )

    buffer.add_ranked_batch(
        [
            _ranked(1, min_mandatory_gap=10),
            _ranked(2, min_mandatory_gap=8),
        ]
    )
    preview = buffer.add_ranked_batch(
        [
            _ranked(3, min_mandatory_gap=3),
            _ranked(4, min_mandatory_gap=9),
        ]
    )

    assert _keys(preview) == [1, 4]


def test_reranking_current_buffer_uses_existing_metrics_without_regeneration() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        ),
        preview_limit=3,
    )
    original_systems = [
        _ranked(1, min_mandatory_gap=10, max_exams_per_day=3),
        _ranked(2, min_mandatory_gap=5, max_exams_per_day=1),
    ]
    buffer.add_ranked_batch(original_systems)

    preview = buffer.rerank(
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.max_exams_per_day,
                    descending=False,
                )
            ]
        )
    )

    assert _keys(preview) == [2, 1]
    assert {id(item) for item in preview} == {id(item) for item in original_systems}


def test_missing_metric_values_are_handled_like_the_existing_ranker() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings(
            [RankingPreference(RankingCriterion.mandatory_span)]
        ),
        preview_limit=2,
    )

    preview = buffer.add_ranked_batch(
        [
            _ranked(1, mandatory_span=MISSING_METRIC_VALUE),
            _ranked(2, mandatory_span=0),
        ]
    )

    assert _keys(preview) == [2, 1]


def test_buffer_returns_safe_list_copies_to_presenters() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings([]),
        preview_limit=2,
    )
    first_preview = buffer.add_ranked_batch([_ranked(1), _ranked(2)])

    first_preview.clear()

    assert _keys(buffer.current_preview()) == [1, 2]


def test_buffer_updates_schedule_counters_when_batches_are_added() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings([]),
        preview_limit=1,
    )

    buffer.add_ranked_batch(
        [_ranked(1), _ranked(2)],
        generated_count=2,
        accepted_count=2,
        processed_count=2,
        ranking_seconds=0.125,
    )

    assert buffer.generated_schedules == 2
    assert buffer.accepted_schedules == 2
    assert buffer.processed_schedules == 2
    assert buffer.systems_seen == 2
    assert buffer.displayed_schedules == 1
    assert buffer.ranking_seconds == 0.125


def test_buffer_handles_empty_batches_without_changing_preview() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        ),
        preview_limit=2,
    )
    buffer.add_ranked_batch([_ranked(1, min_mandatory_gap=5)])

    preview = buffer.add_ranked_batch(
        [],
        generated_count=0,
        accepted_count=0,
        processed_count=0,
        ranking_seconds=0.0,
    )

    assert _keys(preview) == [1]
    assert buffer.generated_schedules == 1
    assert buffer.accepted_schedules == 1
    assert buffer.processed_schedules == 1


def test_buffer_tracks_large_multi_batch_input_while_retaining_only_preview_limit() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        ),
        preview_limit=5,
    )

    for start in range(1, 101, 10):
        batch = [
            _ranked(key, min_mandatory_gap=key)
            for key in range(start, start + 10)
        ]
        preview = buffer.add_ranked_batch(
            batch,
            generated_count=len(batch),
            accepted_count=len(batch),
            processed_count=len(batch),
        )

    assert _keys(preview) == [100, 99, 98, 97, 96]
    assert _keys(buffer.current_preview()) == [100, 99, 98, 97, 96]
    assert buffer.generated_schedules == 100
    assert buffer.accepted_schedules == 100
    assert buffer.processed_schedules == 100
    assert buffer.displayed_schedules == 5


def test_buffer_rejects_negative_progress_counters() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings([]),
        preview_limit=2,
    )

    with pytest.raises(ValueError, match="generated_count"):
        buffer.add_ranked_batch([_ranked(1)], generated_count=-1)

    with pytest.raises(ValueError, match="ranking_seconds"):
        buffer.add_ranked_batch([_ranked(1)], ranking_seconds=-0.1)


def test_buffer_rejects_invalid_preview_limit_updates() -> None:
    buffer = RankedResultsBuffer(
        ranking_settings=RankingSettings([]),
        preview_limit=2,
    )

    with pytest.raises(ValueError, match="preview_limit"):
        buffer.update_preview_limit(0)
