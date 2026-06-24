"""Ranking service for Version 34 schedule optimization.

This module is the boundary between generated schedules and ranked schedules.
The scheduling generator answers "which exam systems are valid?".  This service
answers "how should valid exam systems be ordered according to Section 3
optimization criteria?".

Academic-review orientation
---------------------------
The file demonstrates a deliberate separation of responsibilities:

* ``ScheduleMetricsCalculator`` measures each ``ExamSystem``.
* ``ScheduleRanker`` orders already-measured systems.
* ``ScheduleRankingService`` coordinates those two operations and returns a
  small outcome object with elapsed timing.

This separation is what allows Version 34 to rerank existing processed results
without regenerating schedules or recalculating metrics unnecessarily.
"""
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
    """Result of a ranking action.

    ``ranked_schedules`` carries the ordered ``RankedExamSystem`` wrappers.
    ``elapsed_seconds`` is kept for diagnostics and GUI feedback; it lets the
    presenter report ranking cost without knowing how ranking is implemented.
    """

    ranked_schedules: list[RankedExamSystem]
    elapsed_seconds: float


class ScheduleRankingService:
    """
    Calculates metrics and sorts schedules.

    Re-ranking uses the saved metrics. It does not run the scheduler again.
    Progressive generation uses the batch methods below so the GUI can keep a
    bounded top-N preview instead of retaining every generated exam system.

    Responsibility
    --------------
    The service is intentionally stateless between calls.  Each call receives
    schedules and ranking settings, performs the requested ranking operation,
    and returns an immutable outcome.  This makes the class easy to test and
    safe to reuse from both full-generation and progressive-generation flows.
    """

    def __init__(
        self,
        calculator: ScheduleMetricsCalculator | None = None,
        ranker: ScheduleRanker | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        """Create the ranking service with injectable collaborators.

        Parameters
        ----------
        calculator:
            Calculates Section 3 metric values for each generated schedule.
        ranker:
            Applies ``RankingSettings`` to already-wrapped schedules.
        clock:
            Supplies timing so tests can inject deterministic values.
        """
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

        Parameters
        ----------
        schedules:
            Complete valid exam systems produced by the generator.
        ranking_settings:
            Ordered Section 3 ranking criteria chosen by the user.

        Returns
        -------
        ScheduleRankingOutcome
            Ranked wrappers and timing information.

        Side effects
        ------------
        None.  The method does not persist anything and does not mutate the
        original ``ExamSystem`` objects.
        """
        started_at = self._clock()

        # First convert raw ExamSystem objects into RankedExamSystem wrappers.
        # This is where metrics are calculated exactly once for this ranking
        # pass.  The wrapper keeps the original schedule immutable from the
        # ranking layer's perspective.
        ranked_schedules = self._wrap_with_metrics(
            schedules=schedules,
            starting_schedule_id=1,
        )

        # Sorting is delegated to ScheduleRanker so this service remains an
        # orchestration layer rather than containing comparison logic directly.
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

        This method exists specifically for the progressive Top-N preview.  It
        lets the service rank schedules as soon as a batch is available, instead
        of waiting for the full generator to finish.
        """
        if starting_schedule_id <= 0:
            # Stable positive IDs are part of the ranking/display contract.
            # A zero or negative ID would make generated order tie-breaks
            # ambiguous and user-facing schedule labels harder to reason about.
            raise ValueError("starting_schedule_id must be greater than zero.")

        started_at = self._clock()
        # Metric IDs start at the batch's global start position so every batch
        # participates in one consistent ordering space.
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

        Note
        ----
        ``RankedResultsBuffer`` now owns this policy in the main progressive
        flow.  This method remains useful as an explicit service-level helper
        and documents the same algorithmic idea: merge, sort, trim.
        """
        if display_limit <= 0:
            raise ValueError("display_limit must be greater than zero.")

        # Copy the existing preview first so the caller's list is not mutated.
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
        """Sort existing ranked schedules again.

        The input schedules are already processed ``RankedExamSystem`` objects,
        which means their metrics were calculated earlier.  This method only
        delegates to ``ScheduleRanker`` and never calls the metrics calculator or
        schedule generator.  It is therefore safe for ranking-only setting
        changes where the current ranked buffer should be reordered without
        regenerating schedules.
        """
        started_at = self._clock()

        # No metric calculation appears here by design.  Reranking is a pure
        # ordering operation over already-measured schedules.
        ordered = self._ranker.rank(
            ranked_schedules,
            ranking_settings,
        )

        return ScheduleRankingOutcome(
            ranked_schedules=ordered,
            elapsed_seconds=self._clock() - started_at,
        )

    def rerank_processed_schedules(
        self,
        ranked_schedules: list[RankedExamSystem],
        ranking_settings: RankingSettings,
    ) -> ScheduleRankingOutcome:
        """Compatibility-explicit alias for re-ranking processed results.

        Newer progressive code can use this name when the call site wants to be
        very clear that it is reordering existing ``RankedExamSystem`` wrappers,
        not recalculating metrics and not running the generator again.  The
        existing ``rerank`` method remains the shorter public API used by older
        tests and callers.
        """
        return self.rerank(
            ranked_schedules,
            ranking_settings,
        )

    def _wrap_with_metrics(
        self,
        schedules: list[ExamSystem],
        starting_schedule_id: int,
    ) -> list[RankedExamSystem]:
        """Return RankedExamSystem wrappers for generated schedules.

        Parameters
        ----------
        schedules:
            Raw valid schedules from the generator.
        starting_schedule_id:
            Stable ID assigned to the first schedule in this collection.

        Returns
        -------
        list[RankedExamSystem]
            One wrapper per schedule, preserving the original schedule object
            and attaching calculated metrics.
        """
        # calculate_many() assigns consecutive schedule IDs starting at the
        # provided value.  Progressive ranking depends on this so each batch has
        # globally stable keys instead of restarting at 1.
        metrics = self._calculator.calculate_many(
            schedules,
            starting_schedule_id=starting_schedule_id,
        )
        # zip is safe here because calculate_many() returns exactly one metrics
        # object per input schedule.  The wrapper is the bridge between raw
        # generation output and ranking/display layers.
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
