from __future__ import annotations

from dataclasses import fields

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


def ranked_system(
    key: int,
    *,
    min_mandatory_gap: int = 0,
    average_all_gap: float = 0,
    elective_collision_count: int = 0,
    mandatory_span: int = 0,
    max_exams_per_day: int = 0,
) -> RankedExamSystem:
    """Create a ranked wrapper with explicit metric values."""
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


def keys(
    ranked_systems: list[RankedExamSystem],
) -> list[int]:
    """Return stable ids for simple assertions."""
    return [
        ranked_system.key
        for ranked_system in ranked_systems
    ]


def test_empty_ranking_settings_preserve_input_order() -> None:
    """No selected criteria means no reordering."""
    systems = [
        ranked_system(3),
        ranked_system(1),
        ranked_system(2),
    ]

    ordered = ScheduleRanker().rank(
        systems,
        RankingSettings([]),
    )

    assert ordered == systems
    assert ordered is not systems


def test_descending_criterion_places_larger_metric_first() -> None:
    """Default preference direction is descending."""
    systems = [
        ranked_system(1, min_mandatory_gap=2),
        ranked_system(2, min_mandatory_gap=5),
    ]

    ordered = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.min_mandatory_gap
                )
            ]
        ),
    )

    assert keys(ordered) == [2, 1]


def test_every_ranking_criterion_matches_a_metric_field_and_can_sort() -> None:
    """Each ranking criterion must point to a real metric value."""
    metric_field_names = {
        field.name
        for field in fields(ScheduleMetrics)
    }

    for criterion in RankingCriterion:
        assert criterion.value in metric_field_names

        lower_metrics = {
            current.value: 1
            for current in RankingCriterion
        }
        higher_metrics = dict(lower_metrics)
        higher_metrics[criterion.value] = 2

        systems = [
            ranked_system(1, **lower_metrics),
            ranked_system(2, **higher_metrics),
        ]

        ordered = ScheduleRanker().rank(
            systems,
            RankingSettings(
                [
                    RankingPreference(criterion)
                ]
            ),
        )

        assert keys(ordered) == [2, 1]


def test_ascending_criterion_places_smaller_metric_first() -> None:
    """RankingPreference can explicitly invert a criterion direction."""
    systems = [
        ranked_system(1, elective_collision_count=3),
        ranked_system(2, elective_collision_count=1),
    ]

    ordered = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.elective_collision_count,
                    descending=False,
                )
            ]
        ),
    )

    assert keys(ordered) == [2, 1]


def test_reordering_criteria_changes_result_order() -> None:
    """The first criterion is the primary sort key."""
    systems = [
        ranked_system(1, min_mandatory_gap=10, max_exams_per_day=3),
        ranked_system(2, min_mandatory_gap=5, max_exams_per_day=1),
    ]

    gap_first = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.min_mandatory_gap
                ),
                RankingPreference(
                    RankingCriterion.max_exams_per_day,
                    descending=False,
                ),
            ]
        ),
    )

    max_per_day_first = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.max_exams_per_day,
                    descending=False,
                ),
                RankingPreference(
                    RankingCriterion.min_mandatory_gap
                ),
            ]
        ),
    )

    assert keys(gap_first) == [1, 2]
    assert keys(max_per_day_first) == [2, 1]


def test_equal_metric_values_keep_stable_creation_key_order() -> None:
    """Stable keys make ties deterministic."""
    systems = [
        ranked_system(2, average_all_gap=4),
        ranked_system(1, average_all_gap=4),
    ]

    ordered = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.average_all_gap
                )
            ]
        ),
    )

    assert keys(ordered) == [1, 2]


def test_missing_metric_sorts_after_real_values_in_both_directions() -> None:
    """The sentinel value is never treated as a better real score."""
    systems = [
        ranked_system(1, mandatory_span=MISSING_METRIC_VALUE),
        ranked_system(2, mandatory_span=0),
    ]

    descending = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.mandatory_span
                )
            ]
        ),
    )
    ascending = ScheduleRanker().rank(
        systems,
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.mandatory_span,
                    descending=False,
                )
            ]
        ),
    )

    assert keys(descending) == [2, 1]
    assert keys(ascending) == [2, 1]


def test_ranking_does_not_modify_wrapped_exam_system_objects() -> None:
    """The ranker returns a new order over the same immutable wrappers."""
    first = ranked_system(1, min_mandatory_gap=1)
    second = ranked_system(2, min_mandatory_gap=2)

    ordered = ScheduleRanker().rank(
        [first, second],
        RankingSettings(
            [
                RankingPreference(
                    RankingCriterion.min_mandatory_gap
                )
            ]
        ),
    )

    assert ordered == [second, first]
    assert ordered[0] is second
    assert ordered[1] is first
