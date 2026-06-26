"""Shared data models for Version 34 ranking and optimization.

This module does not calculate metrics and does not sort schedules.  It defines
the vocabulary used by the rest of the ranking architecture:

* which criteria are available;
* how the user orders those criteria;
* where calculated metric values are stored; and
* how a raw ``ExamSystem`` is wrapped once metrics exist.

Academic-review orientation
---------------------------
These models are deliberately small and mostly immutable/value-oriented.  They
make it possible to keep schedule generation separate from schedule ranking:
the generator produces ``ExamSystem`` objects, and the ranking layer attaches
``ScheduleMetrics`` through ``RankedExamSystem`` without mutating the original
domain object.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from scheduling.examScheduleGenerator import ExamSystem


# ---------------------------------------------------------------------------
# Ranking criterion identity (Reqs 3.1 – 3.5)
# ---------------------------------------------------------------------------

class RankingCriterion(Enum):
    """
    Identifies each metric by which a set of exam systems may be ranked.

    Each member corresponds to one numbered requirement from the design
    document (Section 3).  The enum value is a stable string key that can
    be stored in configuration files and compared safely across serialisation
    boundaries.

    * min_mandatory_gap        – Req 3.1: minimum gap (in days) between any
                                 two mandatory exams that share a
                                 (program, year).  Higher is better.
    * average_all_gap          – Req 3.2: mean gap (in days) between every
                                 pair of exams across the whole schedule.
                                 Higher is better.
    * elective_collision_count – Req 3.3: total number of elective-exam
                                 conflicts in the schedule.
                                 Displayed in descending order.
    * mandatory_span           – Req 3.4: span in days from the earliest to
                                 the latest mandatory exam within one program.
                                 Displayed in descending order.
    * max_exams_per_day        – Req 3.5: maximum number of exams placed on
                                 any single calendar day.
                                 Displayed in descending order.
    """

    # Enum values are stable serialization keys. They are used by settings
    # files, cached ranking preferences, GUI controls, and tests. Changing the
    # string values would be a compatibility break even if member names stayed
    # the same.
    min_mandatory_gap = "min_mandatory_gap"
    average_all_gap = "average_all_gap"
    elective_collision_count = "elective_collision_count"
    mandatory_span = "mandatory_span"
    max_exams_per_day = "max_exams_per_day"


# ---------------------------------------------------------------------------
# Per-criterion preference (direction + identity)
# ---------------------------------------------------------------------------

@dataclass
class RankingPreference:
    """
    Pairs one ranking criterion with an explicit sorting direction.

    The current Part 3 product flow uses descending order for every criterion,
    matching Section 3 of the requirements. Keeping the direction inside the
    model still means:

    * The SDD default (descending for all metrics) is honoured by default.
    * Any future requirement to invert a criterion's direction can be handled
      without changing the sorting algorithm.
    * Dan's sorting logic receives a self-describing contract: the same object
      that names the metric also names the direction — no parallel structure
      is needed.

    Fields
    ------
    criterion : RankingCriterion
        The metric this preference applies to.
    descending : bool
        When ``True`` the engine sorts highest value first (e.g.
        ``min_mandatory_gap``, ``average_all_gap``).
        When ``False`` the engine sorts lowest value first (e.g.
        ``elective_collision_count``, ``mandatory_span``,
        ``max_exams_per_day``).
        The SDD requests ``True`` for all five metrics by default; the field
        is exposed explicitly so it can be overridden without subclassing.
    """

    criterion: RankingCriterion
    # Direction is currently descending in the Version 34 GUI, but keeping the
    # field in the model documents the full sorting contract and keeps future
    # direction changes out of ScheduleRanker internals.
    descending: bool = True


# ---------------------------------------------------------------------------
# Active priority profile
# ---------------------------------------------------------------------------

@dataclass
class RankingSettings:
    """
    Represents the active, user-defined ranking priority profile.

    The profile is an ordered list of ``RankingPreference`` objects.  The
    engine applies criteria left-to-right: the first preference is the primary
    sort key, the second is the first tie-breaker, and so on.

    Integrity constraint
    --------------------
    Each ``RankingCriterion`` may appear at most once.  The constructor
    raises ``ValueError`` if a duplicate is detected so the invalid state
    is caught at construction time, not silently ignored by the sorting layer.

    An **empty** list is valid: it represents the user having selected zero
    criteria, in which case the engine preserves the deterministic creation
    order produced by the generator (stable sort).

    Fields
    ------
    priority_list : list[RankingPreference]
        Ordered ranking preferences, highest priority first.
    """

    priority_list: list[RankingPreference]

    def __post_init__(self) -> None:
        """Enforce that no RankingCriterion appears more than once.

        Duplicate criteria would create ambiguous ordering: the same metric
        could act as both a primary sort key and a later tie-breaker. Failing
        fast here keeps invalid settings out of the ranking service.
        """
        seen: set[RankingCriterion] = set()
        for preference in self.priority_list:
            if preference.criterion in seen:
                raise ValueError(
                    f"Duplicate RankingCriterion in priority_list: "
                    f"'{preference.criterion.value}'. "
                    "Each criterion may appear at most once."
                )
            seen.add(preference.criterion)


# ---------------------------------------------------------------------------
# Calculated metric values for one ExamSystem
# ---------------------------------------------------------------------------

MISSING_METRIC_VALUE = -1
# ``-1`` is safe as a sentinel because real metric values are non-negative.
# It lets ranking/display code distinguish "metric unavailable" from a real
# zero value such as "zero elective collisions".


@dataclass(frozen=True)
class ScheduleMetrics:
    """
    Stores the five metric values for one ExamSystem.

    This class only stores data. It does not calculate or sort anything.
    schedule_id is a stable id for the schedule.

    Missing metric rule
    -------------------
    If a metric cannot be calculated, its value is -1.
    Real metric values are zero or higher.

    Fields
    ------
    schedule_id : int
        Stable identifier assigned in generation order.
    min_mandatory_gap : int
        Minimum gap in days between two mandatory exams sharing a
        (program, year).  Corresponds to ``RankingCriterion.min_mandatory_gap``.
    average_all_gap : float
        Mean gap in days between every pair of exams in the schedule.
        Corresponds to ``RankingCriterion.average_all_gap``.
    elective_collision_count : int
        Total elective-exam conflicts in the schedule.
        Corresponds to ``RankingCriterion.elective_collision_count``.
    mandatory_span : int
        Maximum first-to-last mandatory-exam span across eligible
        (program, year, semester, moed) groups.  Corresponds to
        ``RankingCriterion.mandatory_span``.
    max_exams_per_day : int
        Maximum number of exams placed on any single calendar day.
        Corresponds to ``RankingCriterion.max_exams_per_day``.
    """

    schedule_id: int
    # The fields below intentionally mirror ``RankingCriterion`` members.  This
    # one-to-one mapping keeps ScheduleRanker straightforward: each criterion
    # maps directly to one metric attribute.
    min_mandatory_gap: int
    average_all_gap: float
    elective_collision_count: int
    mandatory_span: int
    max_exams_per_day: int


# ---------------------------------------------------------------------------
# Ranked wrapper around one ExamSystem
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RankedExamSystem:
    """
    Holds one ExamSystem with its metrics.

    key is a stable id. It helps keep equal systems in the same order.

    Fields
    ------
    exam_system : ExamSystem
        The complete exam system being ranked.
    metrics : ScheduleMetrics
        Pre-calculated metric values for this system.
    key : int
        Stable, creation-order identifier.  Assigned by the producer;
        never modified after construction.
    """

    exam_system: ExamSystem
    # Metrics are stored beside the schedule so reranking can reuse them without
    # asking the generator or metrics calculator to run again.
    metrics: ScheduleMetrics
    # Stable generation-order key used for deterministic tie-breaking.
    key: int
    # Optional Version 4 fallback metadata.  Strictly valid schedules normally
    # have a penalty score of 0 or None; fallback schedules carry a positive
    # score and human-readable violation details.
    penalty_score: float | None = None
    penalty_details: tuple[str, ...] = ()
    is_fallback: bool = False
