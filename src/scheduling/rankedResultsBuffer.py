"""Bounded ranked-result buffer for progressive generation.

The scheduling generator yields valid ``ExamSystem`` objects lazily.  The
progressive service ranks those systems batch-by-batch and passes the ranked
wrappers into this buffer.  The buffer keeps only the current Top-N preview, not
the full generated history, so it preserves the optimized lazy pipeline.
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
        if self.preview_limit <= 0:
            raise ValueError("preview_limit must be greater than zero.")

    @property
    def systems_seen(self) -> int:
        """Compatibility alias for processed schedules."""
        return self.processed_schedules

    @systems_seen.setter
    def systems_seen(self, value: int) -> None:
        self.processed_schedules = value

    @property
    def ranked_schedules(self) -> list[RankedExamSystem]:
        """Return a safe copy of the current ranked preview."""
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
        """
        batch = list(ranked_batch)
        self._validate_non_negative_counts(
            generated_count=generated_count,
            accepted_count=accepted_count,
            processed_count=processed_count,
            ranking_seconds=ranking_seconds,
        )

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
        """
        if ranking_settings is not None:
            self.ranking_settings = ranking_settings

        self._ranked_preview = self.ranker.rank(
            self._ranked_preview,
            self.ranking_settings,
        )[: self.preview_limit]
        return self.current_preview()

    def update_preview_limit(self, preview_limit: int) -> list[RankedExamSystem]:
        """Change the preview limit for future merges and trim if needed."""
        if preview_limit <= 0:
            raise ValueError("preview_limit must be greater than zero.")

        self.preview_limit = preview_limit
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
        for name, value in {
            "generated_count": generated_count,
            "accepted_count": accepted_count,
            "processed_count": processed_count,
        }.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative.")

        if ranking_seconds < 0:
            raise ValueError("ranking_seconds cannot be negative.")
