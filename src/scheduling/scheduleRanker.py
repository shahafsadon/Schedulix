from __future__ import annotations

from ranking_settings import (
    MISSING_METRIC_VALUE,
    RankedExamSystem,
    RankingCriterion,
    RankingSettings,
    ScheduleMetrics,
)


_METRIC_ATTRIBUTE_BY_CRITERION = {
    RankingCriterion.min_mandatory_gap: "min_mandatory_gap",
    RankingCriterion.average_all_gap: "average_all_gap",
    RankingCriterion.elective_collision_count: "elective_collision_count",
    RankingCriterion.mandatory_span: "mandatory_span",
    RankingCriterion.max_exams_per_day: "max_exams_per_day",
}


class ScheduleRanker:
    """
    Sorts exam systems by the selected metric order.

    The user can choose which metric is first, second, and so on.
    """

    def rank(
        self,
        ranked_systems: list[RankedExamSystem],
        ranking_settings: RankingSettings,
    ) -> list[RankedExamSystem]:
        """
        Return a new list ordered by the configured ranking priorities.

        If no metrics are selected, keep the same order.
        """
        if not ranking_settings.priority_list:
            return list(ranked_systems)

        return sorted(
            ranked_systems,
            key=lambda ranked_system: self._ranking_key(
                ranked_system,
                ranking_settings,
            ),
        )

    def _ranking_key(
        self,
        ranked_system: RankedExamSystem,
        ranking_settings: RankingSettings,
    ) -> tuple[float, ...]:
        """Build the sort key for one ranked system."""
        key_parts: list[float] = []

        for preference in ranking_settings.priority_list:
            value = self._metric_value(
                ranked_system.metrics,
                preference.criterion,
            )

            # Missing metric values should always be last.
            if value == MISSING_METRIC_VALUE:
                key_parts.append(
                    float("inf")
                )
                continue

            if preference.descending:
                key_parts.append(-float(value))
            else:
                key_parts.append(float(value))

        # The stable key keeps equal systems in the same order.
        key_parts.append(float(ranked_system.key))

        return tuple(key_parts)

    @staticmethod
    def _metric_value(
        metrics: ScheduleMetrics,
        criterion: RankingCriterion,
    ) -> int | float:
        """Read one metric value."""
        attribute_name = _METRIC_ATTRIBUTE_BY_CRITERION[criterion]
        return getattr(metrics, attribute_name)
