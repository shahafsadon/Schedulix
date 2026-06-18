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
    Progressive generation uses the batch methods below so the GUI can keep a
    bounded top-N preview instead of retaining every generated exam system.
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

        ranked_schedules = self._wrap_with_metrics(
            schedules=schedules,
            starting_schedule_id=1,
        )

        ordered = self._ranker.rank(
            ranked_schedules,
            ranking_settings,
        )

        return ScheduleRankingOutcome(
            ranked_schedules=ordered,
            elapsed_seconds=self._clock() - started_at,
        )

    def rank_generated_batch(
        self,
        schedules: list[ExamSystem],
        ranking_settings: RankingSettings,
        starting_schedule_id: int,
    ) -> ScheduleRankingOutcome:
        """Rank one generated batch with stable global schedule IDs.

        ``starting_schedule_id`` is the ID assigned to the first schedule in the
        batch.  It prevents every progressive batch from starting again at ID 1,
        which would make tie-breaking unstable and would confuse the GUI.
        """
        if starting_schedule_id <= 0:
            raise ValueError("starting_schedule_id must be greater than zero.")

        started_at = self._clock()
        ranked_schedules = self._wrap_with_metrics(
            schedules=schedules,
            starting_schedule_id=starting_schedule_id,
        )
        ordered = self._ranker.rank(
            ranked_schedules,
            ranking_settings,
        )
        return ScheduleRankingOutcome(
            ranked_schedules=ordered,
            elapsed_seconds=self._clock() - started_at,
        )

    def merge_ranked_preview(
        self,
        existing_preview: list[RankedExamSystem],
        new_ranked_batch: list[RankedExamSystem],
        ranking_settings: RankingSettings,
        display_limit: int,
    ) -> list[RankedExamSystem]:
        """Merge a new ranked batch into the bounded top-N preview.

        The method ranks only ``existing_preview + new_ranked_batch``.  It never
        needs the complete generated history, so memory stays bounded by roughly
        ``display_limit + batch_size``.
        """
        if display_limit <= 0:
            raise ValueError("display_limit must be greater than zero.")

        merged = list(existing_preview)
        merged.extend(new_ranked_batch)
        ordered = self._ranker.rank(
            merged,
            ranking_settings,
        )
        return ordered[:display_limit]

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

    def _wrap_with_metrics(
        self,
        schedules: list[ExamSystem],
        starting_schedule_id: int,
    ) -> list[RankedExamSystem]:
        """Return RankedExamSystem wrappers for generated schedules."""
        metrics = self._calculator.calculate_many(
            schedules,
            starting_schedule_id=starting_schedule_id,
        )
        return [
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
