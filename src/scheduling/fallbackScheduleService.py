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
    ) -> FallbackScheduleOutcome:
        """Return the lowest-penalty hard-valid fallback schedules."""
        if display_limit <= 0:
            raise ValueError("display_limit must be greater than zero.")

        generator = ExamScheduleGenerator(
            constraint_registry=ConstraintRegistry(
                self._penalty_scorer.hard_constraints()
            )
        )
        candidates: list[RankedExamSystem] = []
        generated_count = 0

        for generated_count, exam_system in enumerate(
            generator.iter_exam_systems(courses, exam_periods),
            start=1,
        ):
            candidates.append(
                self._ranked_fallback(
                    exam_system,
                    schedule_id=generated_count,
                    constraint_settings=constraint_settings,
                )
            )

        if not candidates:
            return FallbackScheduleOutcome([], generated_count=0)

        ranked_by_preferences = self._ranker.rank(candidates, ranking_settings)
        ranking_position = {
            ranked_system.key: index
            for index, ranked_system in enumerate(ranked_by_preferences)
        }
        ordered = sorted(
            candidates,
            key=lambda item: (
                float("inf")
                if item.penalty_score is None
                else item.penalty_score,
                ranking_position.get(item.key, item.key),
                item.key,
            ),
        )
        return FallbackScheduleOutcome(
            ranked_schedules=ordered[:display_limit],
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
