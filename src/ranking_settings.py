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
                                 Lower is better (rank descending = False).
    * mandatory_span           – Req 3.4: span in days from the earliest to
                                 the latest mandatory exam within one program.
                                 Lower is better (rank descending = False).
    * max_exams_per_day        – Req 3.5: maximum number of exams placed on
                                 any single calendar day.
                                 Lower is better (rank descending = False).
    """

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

    Keeping the direction inside the model rather than hard-coding it in the
    sorting layer means:

    * The SDD default (descending for all metrics) is honoured by default.
    * Any future requirement to invert a criterion's direction is a one-field
      change in configuration, not a code change in the sorting algorithm.
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
        """Enforce that no RankingCriterion appears more than once."""
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

@dataclass
class ScheduleMetrics:
    """
    Stores the five pre-calculated metric values for one complete ExamSystem.

    This is a pure data holder: it carries no calculation logic.  The metrics
    layer (Dan's component) populates it; the ranking layer reads from it.
    Storing computed values here avoids re-computation during multi-key sorts.

    Fields
    ------
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
        Span in days from the first to the last mandatory exam within any
        single program.  Corresponds to ``RankingCriterion.mandatory_span``.
    max_exams_per_day : int
        Maximum number of exams placed on any single calendar day.
        Corresponds to ``RankingCriterion.max_exams_per_day``.
    """

    min_mandatory_gap: int
    average_all_gap: float
    elective_collision_count: int
    mandatory_span: int
    max_exams_per_day: int


# ---------------------------------------------------------------------------
# Ranked wrapper around one ExamSystem
# ---------------------------------------------------------------------------

@dataclass
class RankedExamSystem:
    """
    Wraps one ``ExamSystem`` together with its metrics and a stable key.

    The key is assigned once by the ranking layer (e.g. a 1-based position
    integer) and survives re-sorts and GUI refresh cycles unchanged.  This
    prevents display flickering when the user adjusts the ranking profile
    and the sort order changes: the key lets the GUI correlate old and new
    list positions without relying on object identity.

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
    metrics: ScheduleMetrics
    key: int
