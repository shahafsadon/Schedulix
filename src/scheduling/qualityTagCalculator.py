"""Create a short quality label for a schedule.

The GUI uses this small helper for snapshot labels. It keeps the quality text
simple: excellent, acceptable, weak, or unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

from ranking_settings import MISSING_METRIC_VALUE, ScheduleMetrics


@dataclass(frozen=True)
class QualityTagResult:
    """A small display label for one schedule quality state."""

    tag: str
    penalty_score: float
    explanation: str


class QualityTagCalculator:
    """Creates a simple quality label from penalty or metric data."""

    def calculate(
        self,
        metrics: ScheduleMetrics | None = None,
        *,
        penalty_score: float | None = None,
    ) -> QualityTagResult:
        """Return a stable quality tag for display and snapshots."""
        if penalty_score is not None:
            return self._from_penalty(penalty_score)

        if metrics is None:
            return QualityTagResult(
                tag="unknown",
                penalty_score=0.0,
                explanation="No metrics or penalty score are available.",
            )

        return self._from_penalty(self._metric_penalty(metrics))

    @staticmethod
    def _from_penalty(penalty_score: float) -> QualityTagResult:
        if penalty_score <= 0:
            tag = "excellent"
        elif penalty_score <= 50:
            tag = "acceptable"
        else:
            tag = "weak"

        return QualityTagResult(
            tag=tag,
            penalty_score=penalty_score,
            explanation=f"Quality tag is based on penalty score {penalty_score:g}.",
        )

    @staticmethod
    def _metric_penalty(metrics: ScheduleMetrics) -> float:
        penalty = 0.0

        if metrics.min_mandatory_gap == MISSING_METRIC_VALUE:
            penalty += 10
        if metrics.average_all_gap == MISSING_METRIC_VALUE:
            penalty += 10
        if metrics.mandatory_span == MISSING_METRIC_VALUE:
            penalty += 10

        penalty += max(metrics.elective_collision_count, 0) * 10
        penalty += max(metrics.max_exams_per_day - 1, 0) * 5
        return penalty
