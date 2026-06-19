"""rankingSettings.py
~~~~~~~~~~~~~~~~~~~~
Value objects that describe how a list of generated exam systems should be
ranked (sorted) for display without restarting the scheduler.

Design notes
------------
* ``RankingCriterion`` is a plain ``Enum`` so it can be stored in a frozen
  dataclass and compared by identity.
* ``RankingSettings`` is a frozen dataclass (immutable) so it is safe to pass
  across thread boundaries and to store as a snapshot.
* Duplicate criteria in the input sequence are **silently removed** (first
  occurrence wins) so callers (e.g. the UI) can hand in raw combo-box values
  without pre-validating for duplicates.
* An **empty** ``criteria`` tuple means "no-op": ``sort_key`` returns a
  constant, so ``sorted()`` preserves the original generation order.

No existing Version 1.0 source files are modified by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scheduling.examScheduleGenerator import ExamSystem


class RankingCriterion(Enum):
    """A single, named dimension along which exam systems are ranked.

    Criteria are applied in the order they appear in
    ``RankingSettings.criteria`` — the first criterion is the primary sort
    key, the second is the tiebreaker, and so on.
    """

    FEWER_EXAM_DAYS = auto()
    """Prefer systems that spread exams across fewer calendar days."""

    MORE_SPREAD = auto()
    """Prefer systems where exam dates span a wider range (start to end)."""

    EARLIER_START = auto()
    """Prefer systems whose earliest exam falls on the earliest calendar date."""


# ---------------------------------------------------------------------------
# Helpers for computing sort keys per criterion
# ---------------------------------------------------------------------------

def _count_distinct_exam_days(system: "ExamSystem") -> int:
    """Return the number of distinct calendar days used by *system*."""
    days: set = set()
    for schedule in system.period_schedules:
        for exam in schedule.scheduled_exams:
            days.add(exam.exam_date)
    return len(days)


def _exam_date_spread(system: "ExamSystem") -> int:
    """Return the span in days from the earliest to the latest exam date.

    Returns 0 for a system with zero or one distinct exam dates.
    A larger span means *more* spread; we negate it in the sort key so that
    systems with more spread sort earlier (ascending sort).
    """
    dates = [
        exam.exam_date
        for schedule in system.period_schedules
        for exam in schedule.scheduled_exams
    ]
    if len(dates) < 2:
        return 0
    return (max(dates) - min(dates)).days


def _earliest_exam_date(system: "ExamSystem"):
    """Return the earliest exam date in *system*, or ``date.max`` if none."""
    from datetime import date as _date
    dates = [
        exam.exam_date
        for schedule in system.period_schedules
        for exam in schedule.scheduled_exams
    ]
    return min(dates) if dates else _date.max


# ---------------------------------------------------------------------------
# RankingSettings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RankingSettings:
    """Immutable specification of how to rank a list of exam systems.

    Parameters
    ----------
    criteria:
        An ordered sequence of ``RankingCriterion`` values.  The first
        element is the primary sort key; later elements act as tiebreakers.
        Duplicates are removed (first occurrence kept) at construction time.
        An empty tuple means "preserve generation order" (no-op).

    Examples
    --------
    >>> settings = RankingSettings.build([
    ...     RankingCriterion.FEWER_EXAM_DAYS,
    ...     RankingCriterion.EARLIER_START,
    ... ])
    >>> sorted_systems = sorted(systems, key=settings.sort_key)
    """

    criteria: tuple[RankingCriterion, ...]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build(cls, criteria: list[RankingCriterion | None]) -> "RankingSettings":
        """Create a ``RankingSettings`` with duplicates and None values removed.

        The first occurrence of each criterion is kept; subsequent duplicates
        are discarded.  ``None`` values are silently skipped so callers can
        pass raw, possibly-incomplete UI values without pre-validating.

        Parameters
        ----------
        criteria:
            Raw (possibly duplicate or None-containing) list of criteria.

        Returns
        -------
        RankingSettings
            A clean, immutable settings object.
        """
        seen: set[RankingCriterion] = set()
        deduped: list[RankingCriterion] = []
        for criterion in criteria:
            if criterion is None:
                continue
            if criterion not in seen:
                seen.add(criterion)
                deduped.append(criterion)
        return cls(criteria=tuple(deduped))

    @classmethod
    def default(cls) -> "RankingSettings":
        """Return the no-op settings that preserve generation order."""
        return cls(criteria=())

    # ------------------------------------------------------------------
    # Sort key
    # ------------------------------------------------------------------

    def sort_key(self, system: "ExamSystem") -> tuple:
        """Return a tuple suitable for use as a ``sorted()`` key.

        Each active criterion contributes one element to the tuple.  The
        sign of each element is chosen so that *lower* values in the
        tuple mean *better* rank (i.e. the system appears earlier after
        an ascending sort).

        An empty ``criteria`` tuple returns ``()`` for every system, so
        ``sorted()`` with this key is effectively a stable no-op.
        """
        key_parts: list = []
        for criterion in self.criteria:
            if criterion is RankingCriterion.FEWER_EXAM_DAYS:
                key_parts.append(_count_distinct_exam_days(system))
            elif criterion is RankingCriterion.MORE_SPREAD:
                key_parts.append(-_exam_date_spread(system))
            elif criterion is RankingCriterion.EARLIER_START:
                key_parts.append(_earliest_exam_date(system))
        return tuple(key_parts)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def is_noop(self) -> bool:
        """Return ``True`` when no criteria are set (generation order preserved)."""
        return len(self.criteria) == 0
