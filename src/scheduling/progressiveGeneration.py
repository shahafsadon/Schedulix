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
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from ranking_settings import RankedExamSystem


class ProgressiveResultState(Enum):
    """Lifecycle state of a progressive generation snapshot."""

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
    """

    batch_size: int = 100
    display_limit: int = 50
    min_update_interval_seconds: float = 0.25
    cache_final_preview: bool = True

    def __post_init__(self) -> None:
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
    """Progress counters exposed to presenters and GUI screens."""

    systems_seen: int
    displayed_count: int
    generated_candidates: int
    accepted_candidates: int
    pruned_candidates: int
    elapsed_seconds: float
    ranking_seconds: float = 0.0


@dataclass(frozen=True)
class ProgressiveRankedSnapshot:
    """Immutable preview/final result emitted during progressive generation."""

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
        """Return True for terminal snapshots."""
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
    """Small mutable helper that keeps only the current ranked preview."""

    ranked_schedules: list[RankedExamSystem] = field(default_factory=list)
    systems_seen: int = 0
    ranking_seconds: float = 0.0
