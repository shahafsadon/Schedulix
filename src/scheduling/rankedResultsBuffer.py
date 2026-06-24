"""Bounded ranked-result buffer for progressive generation.

The scheduling generator yields valid ``ExamSystem`` objects lazily.  The
progressive service ranks those systems batch-by-batch and passes the ranked
wrappers into this buffer.  The buffer keeps only the current Top-N preview, not
the full generated history, so it preserves the optimized lazy pipeline.

Academic-review orientation
---------------------------
This module is the core memory-management component of Version 34's
Progressive Top-N Preview.  It explains the main tradeoff clearly:

* keeping every generated schedule maximizes reranking flexibility but can use
  too much memory;
* keeping only a bounded preview protects responsiveness and memory usage but
  intentionally discards schedules outside the current Top-N.

The scheduling service owns the workflow.  This buffer owns only the retention
policy: merge incoming ranked batches, sort them using the active ranking
settings, and keep at most ``preview_limit`` schedules.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ranking_settings import RankedExamSystem, RankingSettings
from scheduling.scheduleRanker import ScheduleRanker


@dataclass
class RankedResultsBuffer:
    """Maintain the best ranked schedules seen so far.

    ``RankedExamSystem`` already stores both the generated exam system and its
    calculated metrics.  This buffer therefore never recalculates metrics and
    never asks the schedule generator for more data.  It only merges ranked
    batches, re-applies the existing stable ranker, and returns defensive list
    copies for presenters.

    Responsibility
    --------------
    The class deliberately does not call ``ExamScheduleGenerator`` and does not
    calculate metrics.  That separation makes the pipeline easy to explain:

    ``ScheduleRankingService`` calculates metrics and ranks a batch;
    ``RankedResultsBuffer`` decides which ranked schedules remain visible.

    Side effects
    ------------
    Methods mutate the in-memory preview and counters.  They never write to
    disk or to ``CacheManager``; persistence remains the service's decision.
    """

    ranking_settings: RankingSettings
    preview_limit: int = 50
    ranker: ScheduleRanker = field(default_factory=ScheduleRanker)
    generated_schedules: int = 0
    accepted_schedules: int = 0
    processed_schedules: int = 0
    ranking_seconds: float = 0.0
    _ranked_preview: list[RankedExamSystem] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        # A non-positive preview limit would make the Top-N contract undefined:
        # the GUI expects at least one retained schedule when any valid result
        # exists, and slicing with zero would silently hide useful work.
        if self.preview_limit <= 0:
            raise ValueError("preview_limit must be greater than zero.")

    @property
    def systems_seen(self) -> int:
        """Compatibility alias for processed schedules.

        Older presenter code uses ``systems_seen`` terminology.  Internally the
        buffer tracks ``processed_schedules`` because the value represents
        schedules whose ranking/metrics have been processed, not raw candidate
        placements inside the recursive generator.
        """
        return self.processed_schedules

    @systems_seen.setter
    def systems_seen(self, value: int) -> None:
        self.processed_schedules = value

    @property
    def ranked_schedules(self) -> list[RankedExamSystem]:
        """Return a safe copy of the current ranked preview.

        Returning a copy protects the buffer from accidental mutation by a GUI
        presenter or test.  The buffer is the single owner of preview state.
        """
        return self.current_preview()

    @ranked_schedules.setter
    def ranked_schedules(self, value: Iterable[RankedExamSystem]) -> None:
        self.replace_preview(value)

    @property
    def displayed_schedules(self) -> int:
        """Number of schedules currently retained for display."""
        return len(self._ranked_preview)

    def add_ranked_batch(
        self,
        ranked_batch: Iterable[RankedExamSystem],
        *,
        generated_count: int | None = None,
        accepted_count: int | None = None,
        processed_count: int | None = None,
        ranking_seconds: float = 0.0,
    ) -> list[RankedExamSystem]:
        """Merge one newly ranked batch into the bounded preview.

        The returned list is a defensive copy.  Existing better schedules remain
        in the buffer because the ranker is applied to ``current preview + new
        batch`` before the preview limit is enforced.

        Algorithmic idea
        ----------------
        Only two sets are ever needed for this step:

        1. the schedules currently visible in the Top-N preview;
        2. the newly processed ranked batch.

        The method merges those two sets, ranks the merged list, and trims it
        back to ``preview_limit``.  This is why memory stays bounded by roughly
        ``preview_limit + batch_size`` instead of the total number of generated
        schedules.
        """
        # Materialize the iterable once so it can be counted and merged safely.
        # The caller may pass a generator, but the buffer needs a stable batch
        # snapshot for counter updates and ranking.
        batch = list(ranked_batch)
        self._validate_non_negative_counts(
            generated_count=generated_count,
            accepted_count=accepted_count,
            processed_count=processed_count,
            ranking_seconds=ranking_seconds,
        )

        # Count parameters are optional because some older callers only pass a
        # ranked batch.  In that case len(batch) is the best available count.
        default_count = len(batch)
        self.generated_schedules += (
            default_count if generated_count is None else generated_count
        )
        self.accepted_schedules += (
            default_count if accepted_count is None else accepted_count
        )
        self.processed_schedules += (
            default_count if processed_count is None else processed_count
        )
        self.ranking_seconds += ranking_seconds

        if batch:
            # Core Top-N operation: allow the new batch to challenge the
            # current preview, then enforce the display limit immediately.
            merged = [*self._ranked_preview, *batch]
            self._ranked_preview = self.ranker.rank(
                merged,
                self.ranking_settings,
            )[: self.preview_limit]

        return self.current_preview()

    def rerank(
        self,
        ranking_settings: RankingSettings | None = None,
    ) -> list[RankedExamSystem]:
        """Re-rank the retained preview without regenerating schedules.

        This is intentionally limited to schedules already held in the buffer.
        A product flow that needs a globally correct Top-N under brand-new
        ranking settings while generation is active should still restart the
        progressive run, because discarded schedules are not retained here.

        Important assumption
        --------------------
        Every retained item is already a ``RankedExamSystem`` with calculated
        metrics.  Therefore reranking here is only a sorting operation, not a
        metric-recalculation or generation operation.
        """
        if ranking_settings is not None:
            # Changing settings here affects future batch merges too, not just
            # the immediate reorder of the retained preview.
            self.ranking_settings = ranking_settings

        self._ranked_preview = self.ranker.rank(
            self._ranked_preview,
            self.ranking_settings,
        )[: self.preview_limit]
        return self.current_preview()

    def update_preview_limit(self, preview_limit: int) -> list[RankedExamSystem]:
        """Change the preview limit for future merges and trim if needed.

        This supports future UI controls that may let users choose a larger or
        smaller preview.  Lowering the limit is destructive for schedules that
        fall outside the new preview; that is consistent with the bounded
        memory contract.
        """
        if preview_limit <= 0:
            raise ValueError("preview_limit must be greater than zero.")

        self.preview_limit = preview_limit
        # Trimming immediately keeps the object invariant true: the retained
        # preview length should never exceed preview_limit after this method.
        self._ranked_preview = self._ranked_preview[: self.preview_limit]
        return self.current_preview()

    def replace_preview(
        self,
        ranked_schedules: Iterable[RankedExamSystem],
    ) -> list[RankedExamSystem]:
        """Replace the buffer contents with ranked schedules.

        This method is mainly for compatibility with earlier progressive helper
        code and tests.  The provided schedules are sorted using the active
        ranking settings before being stored.

        Side effect
        -----------
        Replaces the retained preview but does not update generation counters.
        It is therefore useful for controlled setup/compatibility paths rather
        than for normal batch-processing progress accounting.
        """
        self._ranked_preview = self.ranker.rank(
            list(ranked_schedules),
            self.ranking_settings,
        )[: self.preview_limit]
        return self.current_preview()

    def current_preview(self) -> list[RankedExamSystem]:
        """Return a defensive list copy of the current ranked preview."""
        return list(self._ranked_preview)

    @staticmethod
    def _validate_non_negative_counts(
        *,
        generated_count: int | None,
        accepted_count: int | None,
        processed_count: int | None,
        ranking_seconds: float,
    ) -> None:
        """Reject impossible progress counters before they corrupt UI state."""
        for name, value in {
            "generated_count": generated_count,
            "accepted_count": accepted_count,
            "processed_count": processed_count,
        }.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative.")

        if ranking_seconds < 0:
            raise ValueError("ranking_seconds cannot be negative.")
