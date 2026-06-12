from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from ranking_settings import RankedExamSystem, RankingSettings
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.scheduleMetricsCalculator import ScheduleMetricsCalculator
from scheduling.scheduleRanker import ScheduleRanker


@dataclass(frozen=True)
class ScheduleRankingOutcome:
    """Result of a ranking action."""

    ranked_schedules: list[RankedExamSystem]
    elapsed_seconds: float


class ScheduleRankingService:
    """
    Calculates metrics and sorts schedules.

    Re-ranking uses the saved metrics. It does not run the scheduler again.
    """

    def __init__(
        self,
        calculator: ScheduleMetricsCalculator | None = None,
        ranker: ScheduleRanker | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._calculator = calculator or ScheduleMetricsCalculator()
        self._ranker = ranker or ScheduleRanker()
        self._clock = clock

    def rank_generated_schedules(
        self,
        schedules: list[ExamSystem],
        ranking_settings: RankingSettings,
    ) -> ScheduleRankingOutcome:
        """
        Calculate metrics once, then return schedules in ranked order.

        The original ExamSystem objects are not changed.
        """
        started_at = self._clock()

        metrics = self._calculator.calculate_many(schedules)
        ranked_schedules = [
            RankedExamSystem(
                exam_system=schedule,
                metrics=schedule_metrics,
                key=schedule_metrics.schedule_id,
            )
            for schedule, schedule_metrics in zip(
                schedules,
                metrics,
            )
        ]

        ordered = self._ranker.rank(
            ranked_schedules,
            ranking_settings,
        )

        return ScheduleRankingOutcome(
            ranked_schedules=ordered,
            elapsed_seconds=self._clock() - started_at,
        )

    def rerank(
        self,
        ranked_schedules: list[RankedExamSystem],
        ranking_settings: RankingSettings,
    ) -> ScheduleRankingOutcome:
        """Sort existing ranked schedules again."""
        started_at = self._clock()

        ordered = self._ranker.rank(
            ranked_schedules,
            ranking_settings,
        )

        return ScheduleRankingOutcome(
            ranked_schedules=ordered,
            elapsed_seconds=self._clock() - started_at,
        )
