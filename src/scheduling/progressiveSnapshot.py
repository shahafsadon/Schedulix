"""progressiveSnapshot.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Data container representing an in-flight or completed generation result,
paired with the ranking settings applied to it (SCRUM-184).

Design
------
``ProgressiveRankedSnapshot`` has two states:

``PARTIAL``
    Generation is still running.  The ``schedules`` list contains only the
    systems produced so far.  A PARTIAL snapshot is kept **in-memory only**
    and must **never** be written to the cache.

``COMPLETE``
    Generation has finished successfully.  The ``schedules`` list is the full,
    ranked result.  Only a COMPLETE snapshot may be persisted to the cache.

The ``SnapshotState`` enum and the dataclass together form the only gate that
enforces this invariant; callers are expected to check ``snapshot.is_complete``
before calling any ``CacheManager`` setter.

No existing Version 1.0 source files are modified by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scheduling.examScheduleGenerator import ExamSystem
    from scheduling.rankingSettings import RankingSettings


class SnapshotState(Enum):
    """The two observable states of a progressive generation run.

    ``PARTIAL``
        Work is still in progress.  The snapshot must stay in memory.

    ``COMPLETE``
        Work has finished.  The snapshot may be written to the cache.
    """

    PARTIAL = auto()
    COMPLETE = auto()


@dataclass
class ProgressiveRankedSnapshot:
    """Holds a (possibly incomplete) ranked list of generated exam systems.

    Attributes
    ----------
    state:
        ``PARTIAL`` while generation is running; ``COMPLETE`` when it has
        finished.  Code that writes to the cache **must** check this first.
    schedules:
        The ranked list of exam systems available at this point in time.
        When ``state`` is ``PARTIAL`` more systems may arrive later.
    ranking_settings:
        The ``RankingSettings`` object used to sort ``schedules``.
        Stored alongside the schedules so that the output screen can
        display the active ranking and the cache can round-trip it.
    """

    state: SnapshotState
    schedules: list["ExamSystem"]
    ranking_settings: "RankingSettings"

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        """``True`` when this snapshot may be safely written to the cache."""
        return self.state is SnapshotState.COMPLETE

    @property
    def is_partial(self) -> bool:
        """``True`` while generation is still running."""
        return self.state is SnapshotState.PARTIAL

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def partial(
        cls,
        schedules: list["ExamSystem"],
        ranking_settings: "RankingSettings",
    ) -> "ProgressiveRankedSnapshot":
        """Create an in-progress snapshot that must not be persisted."""
        return cls(
            state=SnapshotState.PARTIAL,
            schedules=list(schedules),
            ranking_settings=ranking_settings,
        )

    @classmethod
    def complete(
        cls,
        schedules: list["ExamSystem"],
        ranking_settings: "RankingSettings",
    ) -> "ProgressiveRankedSnapshot":
        """Create a completed snapshot that is safe to persist."""
        return cls(
            state=SnapshotState.COMPLETE,
            schedules=list(schedules),
            ranking_settings=ranking_settings,
        )

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def with_ranking(self, new_settings: "RankingSettings") -> "ProgressiveRankedSnapshot":
        """Return a new snapshot with schedules re-sorted by *new_settings*.

        The original snapshot is not mutated.  The returned snapshot has the
        same ``state`` as the original so the PARTIAL/COMPLETE contract is
        preserved across re-ranking calls.

        If ``new_settings.is_noop()`` the schedule order is left unchanged.
        """
        if new_settings.is_noop():
            return ProgressiveRankedSnapshot(
                state=self.state,
                schedules=list(self.schedules),
                ranking_settings=new_settings,
            )
        return ProgressiveRankedSnapshot(
            state=self.state,
            schedules=sorted(self.schedules, key=new_settings.sort_key),
            ranking_settings=new_settings,
        )
