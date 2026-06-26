"""Best-effort fallback schedule generation.

This service runs only after strict generation returns zero valid schedules.
It keeps hard red-line constraints enforced, relaxes enabled soft thresholds,
and ranks hard-valid alternatives by penalty score.
"""

from __future__ import annotations

from dataclasses import dataclass

from constraint_settings import SchedulingConstraintSettings
from ranking_settings import RankedExamSystem, RankingSettings
from scheduling.constraints import ConstraintRegistry
from scheduling.examScheduleGenerator import ExamScheduleGenerator, ExamSystem
from scheduling.rankedResultsBuffer import RankedResultsBuffer
from scheduling.scheduleMetricsCalculator import ScheduleMetricsCalculator
from scheduling.schedulePenaltyScorer import SchedulePenaltyScorer
from scheduling.scheduleRanker import ScheduleRanker


@dataclass(frozen=True)
class FallbackScheduleOutcome:
    """Best fallback alternatives produced under hard constraints only."""

    ranked_schedules: list[RankedExamSystem]
    generated_count: int


class FallbackScheduleService:
    """Generate hard-valid alternatives and rank them by soft penalty."""

    def __init__(
        self,
        penalty_scorer: SchedulePenaltyScorer | None = None,
        metrics_calculator: ScheduleMetricsCalculator | None = None,
        ranker: ScheduleRanker | None = None,
    ) -> None:
        self._penalty_scorer = penalty_scorer or SchedulePenaltyScorer()
        self._metrics_calculator = metrics_calculator or ScheduleMetricsCalculator()
        self._ranker = ranker or ScheduleRanker()

    def generate_best_alternatives(
        self,
        courses: list,
        exam_periods: list,
        constraint_settings: SchedulingConstraintSettings | None,
        ranking_settings: RankingSettings,
        *,
        display_limit: int,
        batch_size: int = 100,
    ) -> FallbackScheduleOutcome:
        """Return the lowest-penalty hard-valid fallback schedules.

        Candidates are processed in small batches and merged into a bounded
        Top-N buffer. This avoids recreating the old memory problem precisely
        when a strict run has already found no result.
        """
        if display_limit <= 0:
            raise ValueError("display_limit must be greater than zero.")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        generator = ExamScheduleGenerator(
            constraint_registry=ConstraintRegistry(
                self._penalty_scorer.hard_constraints()
            )
        )
        preview = RankedResultsBuffer(
            ranking_settings=ranking_settings,
            preview_limit=display_limit,
            ranker=self._ranker,
        )
        batch: list[RankedExamSystem] = []
        generated_count = 0

        for generated_count, exam_system in enumerate(
            generator.iter_exam_systems(courses, exam_periods),
            start=1,
        ):
            batch.append(
                self._ranked_fallback(
                    exam_system,
                    schedule_id=generated_count,
                    constraint_settings=constraint_settings,
                )
            )
            if len(batch) == batch_size:
                preview.add_ranked_batch(
                    batch,
                    generated_count=len(batch),
                    accepted_count=len(batch),
                    processed_count=len(batch),
                )
                batch = []

        if batch:
            preview.add_ranked_batch(
                batch,
                generated_count=len(batch),
                accepted_count=len(batch),
                processed_count=len(batch),
            )

        if generated_count == 0:
            return FallbackScheduleOutcome([], generated_count=0)

        return FallbackScheduleOutcome(
            ranked_schedules=preview.current_preview(),
            generated_count=generated_count,
        )

    def _ranked_fallback(
        self,
        exam_system: ExamSystem,
        *,
        schedule_id: int,
        constraint_settings: SchedulingConstraintSettings | None,
    ) -> RankedExamSystem:
        metrics = self._metrics_calculator.calculate(
            exam_system,
            schedule_id=schedule_id,
        )
        penalty = self._penalty_scorer.score(exam_system, constraint_settings)
        return RankedExamSystem(
            exam_system=exam_system,
            metrics=metrics,
            key=schedule_id,
            penalty_score=penalty.total_score,
            penalty_details=penalty.details,
            is_fallback=True,
        )
