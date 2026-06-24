"""Progressive schedule-generation contracts.

This module contains the small data contracts used by the progressive
schedule-generation flow.  They intentionally live outside the GUI and outside
``ExamScheduleGenerator``:

* the generator keeps doing optimized lazy generation;
* the scheduling service owns batching and ranking previews;
* the async runner owns background execution and cancellation;
* the GUI/presenter only consume immutable snapshots.

The goal is to expose partial ranked results without reintroducing the old
"materialize every complete system before ranking/display" bottleneck.

Academic-review orientation
---------------------------
The classes here are intentionally simple data contracts.  They make the
progressive pipeline explainable during review: the scheduling service can
publish a structured snapshot, the presenter can translate it into GUI text,
and the GUI never needs to inspect mutable service internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from scheduling.batchIterator import (
    GeneratedScheduleBatch,
    batch_exam_systems,
    iter_batches,
    iter_exam_system_batches,
    iter_fixed_size_batches,
)

from ranking_settings import RankedExamSystem


class ProgressiveResultState(Enum):
    """Lifecycle state of a progressive generation snapshot.

    ``PARTIAL`` snapshots are temporary progress updates.  ``COMPLETE``,
    ``CANCELLED``, and ``FAILED`` are terminal states that tell the presenter
    the background run has ended and final UI state can be shown.
    """

    PARTIAL = auto()
    COMPLETE = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class ProgressiveGenerationOptions:
    """Runtime knobs for progressive generation and preview ranking.

    ``batch_size`` controls how many lazily-generated complete exam systems are
    consumed before the service considers publishing a preview update.
    ``display_limit`` controls how many ranked systems are retained for the GUI.

    The defaults are deliberately conservative: frequent enough to feel alive,
    but bounded enough to avoid turning the GUI cache into a giant materialized
    result set.

    Parameters
    ----------
    batch_size:
        Number of complete exam systems processed per ranking batch.
    display_limit:
        Maximum number of ranked schedules retained for preview.
    min_update_interval_seconds:
        Minimum time between emitted partial snapshots.  This protects the GUI
        event queue from excessive updates on fast runs.
    cache_final_preview:
        Whether a complete progressive run should persist the final bounded
        preview to ``CacheManager``.
    """

    batch_size: int = 100
    display_limit: int = 50
    min_update_interval_seconds: float = 0.25
    cache_final_preview: bool = True

    def __post_init__(self) -> None:
        """Validate runtime knobs before a progressive run starts.

        The checks are edge-case guards: invalid values would otherwise produce
        confusing behavior such as empty previews, infinite loops, or negative
        timing thresholds.
        """
        if self.batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")
        if self.display_limit <= 0:
            raise ValueError("display_limit must be greater than zero.")
        if self.min_update_interval_seconds < 0:
            raise ValueError(
                "min_update_interval_seconds cannot be negative."
            )


@dataclass(frozen=True)
class ProgressiveCounters:
    """Progress counters exposed to presenters and GUI screens.

    ``systems_seen`` and ``displayed_count`` are kept for compatibility with the
    previous progressive-planning patch. The explicit schedule-count fields are
    the task-level counters requested for the batched processing layer:

    * generated schedules: valid ``ExamSystem`` objects consumed from the lazy
      generator;
    * accepted schedules: valid generated systems accepted into the progressive
      pipeline;
    * processed schedules: systems whose metrics/ranking were actually
      calculated;
    * displayed schedules: ranked systems currently retained for the GUI
      preview.

    Candidate counters still come from ``ExamScheduleGenerator.diagnostics`` and
    describe recursive placement attempts, not complete exam systems.

    Important distinction
    ---------------------
    Candidate counters explain the internal scheduling algorithm.  Schedule
    counters explain user-visible progress through complete ``ExamSystem``
    objects.  Both are exposed because an academic review may ask about both
    pruning efficiency and GUI progress.
    """

    systems_seen: int
    displayed_count: int
    generated_candidates: int
    accepted_candidates: int
    pruned_candidates: int
    elapsed_seconds: float
    ranking_seconds: float = 0.0
    generated_schedule_count: int | None = None
    accepted_schedule_count: int | None = None
    processed_schedule_count: int | None = None
    displayed_schedule_count: int | None = None

    def __post_init__(self) -> None:
        """Fill explicit schedule counters from legacy fields when omitted."""
        # ``object.__setattr__`` is required because the dataclass is frozen.
        # The object remains immutable after construction, but this hook lets us
        # normalize missing compatibility fields during initialization.
        if self.generated_schedule_count is None:
            object.__setattr__(
                self,
                "generated_schedule_count",
                self.systems_seen,
            )
        if self.accepted_schedule_count is None:
            object.__setattr__(
                self,
                "accepted_schedule_count",
                self.generated_schedule_count,
            )
        if self.processed_schedule_count is None:
            object.__setattr__(
                self,
                "processed_schedule_count",
                self.systems_seen,
            )
        if self.displayed_schedule_count is None:
            object.__setattr__(
                self,
                "displayed_schedule_count",
                self.displayed_count,
            )

    @property
    def generated_schedules(self) -> int:
        """Alias for the valid schedules consumed from the generator."""
        return int(self.generated_schedule_count or 0)

    @property
    def accepted_schedules(self) -> int:
        """Alias for schedules accepted into the progressive pipeline."""
        return int(self.accepted_schedule_count or 0)

    @property
    def processed_schedules(self) -> int:
        """Alias for schedules whose metrics/ranking were processed."""
        return int(self.processed_schedule_count or 0)

    @property
    def displayed_schedules(self) -> int:
        """Alias for schedules currently displayed in the ranked preview."""
        return int(self.displayed_schedule_count or 0)


@dataclass(frozen=True)
class ProgressiveRankedSnapshot:
    """Immutable preview/final result emitted during progressive generation.

    The snapshot is the contract between the scheduling service and the GUI
    layer.  It carries the current ranked preview, progress counters, lifecycle
    state, and a human-readable message.  Keeping it frozen prevents accidental
    mutation after the service publishes it.
    """

    run_id: int
    state: ProgressiveResultState
    ranked_schedules: list[RankedExamSystem]
    counters: ProgressiveCounters
    relevant_course_count: int
    ranking_version: int
    message: str
    error: str | None = None

    @property
    def is_final(self) -> bool:
        """Return True for terminal snapshots.

        Presenters use this to decide whether the run is still producing live
        updates or whether final UI controls can be enabled.
        """
        return self.state in {
            ProgressiveResultState.COMPLETE,
            ProgressiveResultState.CANCELLED,
            ProgressiveResultState.FAILED,
        }

    @property
    def is_partial(self) -> bool:
        """Return True while generation is still running."""
        return self.state == ProgressiveResultState.PARTIAL


@dataclass
class ProgressivePreviewBuffer:
    """Small mutable helper that keeps only the current ranked preview.

    This class is retained for compatibility with earlier progressive helper
    code.  The main Version 34 Top-N retention policy now lives in
    ``RankedResultsBuffer``, which additionally knows how to merge and rerank
    batches.  This simpler buffer still documents the minimal state needed for
    a preview: retained ranked schedules plus counters.
    """

    ranked_schedules: list[RankedExamSystem] = field(default_factory=list)
    generated_schedules: int = 0
    accepted_schedules: int = 0
    processed_schedules: int = 0
    ranking_seconds: float = 0.0

    @property
    def systems_seen(self) -> int:
        """Compatibility alias for processed schedules."""
        return self.processed_schedules

    @systems_seen.setter
    def systems_seen(self, value: int) -> None:
        self.processed_schedules = value
