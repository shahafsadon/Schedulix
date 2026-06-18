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
from scheduling.scheduleRanker import ScheduleRanker
from scheduling.scheduleRankingService import ScheduleRankingService


def _exam_system() -> ExamSystem:
    return ExamSystem(period_schedules=[])


def _metrics(
    schedule_id: int,
    *,
    min_mandatory_gap: int = 0,
    average_all_gap: float = 0,
    elective_collision_count: int = 0,
    mandatory_span: int = 0,
    max_exams_per_day: int = 0,
) -> ScheduleMetrics:
    return ScheduleMetrics(
        schedule_id=schedule_id,
        min_mandatory_gap=min_mandatory_gap,
        average_all_gap=average_all_gap,
        elective_collision_count=elective_collision_count,
        mandatory_span=mandatory_span,
        max_exams_per_day=max_exams_per_day,
    )


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
        exam_system=_exam_system(),
        metrics=_metrics(
            key,
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


class RecordingCalculator:
    def __init__(self) -> None:
        self.calls: list[tuple[list[ExamSystem], int]] = []

    def calculate_many(
        self,
        exam_systems: list[ExamSystem],
        starting_schedule_id: int = 1,
    ) -> list[ScheduleMetrics]:
        systems = list(exam_systems)
        self.calls.append((systems, starting_schedule_id))
        return [
            _metrics(
                schedule_id,
                min_mandatory_gap=schedule_id,
            )
            for schedule_id, _ in enumerate(
                systems,
                start=starting_schedule_id,
            )
        ]


class RecordingRanker:
    def __init__(self) -> None:
        self.calls: list[tuple[list[RankedExamSystem], RankingSettings]] = []

    def rank(
        self,
        ranked_systems: list[RankedExamSystem],
        ranking_settings: RankingSettings,
    ) -> list[RankedExamSystem]:
        ranked = list(ranked_systems)
        self.calls.append((ranked, ranking_settings))
        return list(reversed(ranked))


class ExplodingCalculator:
    def calculate_many(
        self,
        exam_systems: list[ExamSystem],
        starting_schedule_id: int = 1,
    ) -> list[ScheduleMetrics]:
        raise AssertionError("Metrics should not be recalculated during rerank.")


def test_batch_ranking_uses_same_metric_logic_as_full_ranking() -> None:
    service = ScheduleRankingService()
    schedules = [_exam_system(), _exam_system(), _exam_system()]
    settings = RankingSettings(
        [RankingPreference(RankingCriterion.min_mandatory_gap)]
    )

    full_outcome = service.rank_generated_schedules(
        schedules,
        settings,
    )
    batch_outcome = service.rank_generated_batch(
        schedules,
        settings,
        starting_schedule_id=1,
    )

    assert [ranked.metrics for ranked in batch_outcome.ranked_schedules] == [
        ranked.metrics for ranked in full_outcome.ranked_schedules
    ]
    assert _keys(batch_outcome.ranked_schedules) == _keys(
        full_outcome.ranked_schedules
    )


def test_full_ranking_keeps_backward_compatible_schedule_ids() -> None:
    service = ScheduleRankingService()
    schedules = [_exam_system(), _exam_system()]

    outcome = service.rank_generated_schedules(
        schedules,
        RankingSettings([]),
    )

    assert _keys(outcome.ranked_schedules) == [1, 2]
    assert [ranked.metrics.schedule_id for ranked in outcome.ranked_schedules] == [
        1,
        2,
    ]


def test_batch_ranking_assigns_stable_global_schedule_ids() -> None:
    service = ScheduleRankingService()
    schedules = [_exam_system(), _exam_system(), _exam_system()]

    outcome = service.rank_generated_batch(
        schedules,
        RankingSettings([]),
        starting_schedule_id=25,
    )

    assert _keys(outcome.ranked_schedules) == [25, 26, 27]
    assert [ranked.metrics.schedule_id for ranked in outcome.ranked_schedules] == [
        25,
        26,
        27,
    ]


def test_batch_ranking_calculates_metrics_once_and_reuses_ranker() -> None:
    calculator = RecordingCalculator()
    ranker = RecordingRanker()
    service = ScheduleRankingService(
        calculator=calculator,  # type: ignore[arg-type]
        ranker=ranker,  # type: ignore[arg-type]
    )
    schedules = [_exam_system(), _exam_system()]
    settings = RankingSettings([])

    outcome = service.rank_generated_batch(
        schedules,
        settings,
        starting_schedule_id=10,
    )

    assert len(calculator.calls) == 1
    assert calculator.calls[0] == (schedules, 10)
    assert len(ranker.calls) == 1
    assert ranker.calls[0][1] is settings
    assert _keys(outcome.ranked_schedules) == [11, 10]


def test_batch_ranking_rejects_invalid_starting_schedule_id() -> None:
    service = ScheduleRankingService()

    with pytest.raises(ValueError, match="starting_schedule_id"):
        service.rank_generated_batch(
            [_exam_system()],
            RankingSettings([]),
            starting_schedule_id=0,
        )


def test_batch_ranking_handles_missing_metric_values_like_existing_ranker() -> None:
    class MissingMetricCalculator:
        def calculate_many(
            self,
            exam_systems: list[ExamSystem],
            starting_schedule_id: int = 1,
        ) -> list[ScheduleMetrics]:
            return [
                _metrics(
                    starting_schedule_id,
                    mandatory_span=MISSING_METRIC_VALUE,
                ),
                _metrics(
                    starting_schedule_id + 1,
                    mandatory_span=0,
                ),
            ]

    service = ScheduleRankingService(
        calculator=MissingMetricCalculator(),  # type: ignore[arg-type]
        ranker=ScheduleRanker(),
    )

    outcome = service.rank_generated_batch(
        [_exam_system(), _exam_system()],
        RankingSettings(
            [RankingPreference(RankingCriterion.mandatory_span)]
        ),
        starting_schedule_id=1,
    )

    assert _keys(outcome.ranked_schedules) == [2, 1]


def test_rerank_reports_elapsed_seconds_without_recalculating_metrics() -> None:
    """Ranking-only changes should return a measured response time."""
    times = iter([10.0, 10.125])
    service = ScheduleRankingService(
        calculator=ExplodingCalculator(),  # type: ignore[arg-type]
        clock=lambda: next(times),
    )
    existing = [_ranked(1), _ranked(2)]

    outcome = service.rerank(
        existing,
        RankingSettings([]),
    )

    assert outcome.ranked_schedules == existing
    assert outcome.elapsed_seconds == 0.125


def test_rerank_processed_schedules_is_explicit_alias_for_rerank() -> None:
    service = ScheduleRankingService(
        calculator=ExplodingCalculator(),  # type: ignore[arg-type]
    )
    existing = [
        _ranked(1, max_exams_per_day=3),
        _ranked(2, max_exams_per_day=1),
    ]

    outcome = service.rerank_processed_schedules(
        existing,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.max_exams_per_day,
                    descending=False,
                )
            ]
        ),
    )

    assert _keys(outcome.ranked_schedules) == [2, 1]
