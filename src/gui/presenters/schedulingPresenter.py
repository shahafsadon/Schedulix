"""Presenter for triggering schedule generation.

The presenter keeps GUI code out of the scheduling service.  ``generate()`` is
kept for the existing full-materialization flow, while ``generate_progressive``
uses the service's lazy batched ranking path and forwards snapshots to the view.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from application.cache_manager import CacheManager
from scheduling.progressiveGeneration import (
    ProgressiveGenerationOptions,
    ProgressiveRankedSnapshot,
    ProgressiveResultState,
)
from scheduling.schedulingService import SchedulingService


@dataclass(frozen=True)
class GenerationResult:
    """Display-ready outcome of a generation attempt."""

    success: bool
    message: str
    schedule_count: int = 0
    pruned_candidates: int = 0
    displayed_count: int = 0
    partial: bool = False


class SchedulingPresenter:
    """Drives the schedule-generation step of the wizard."""

    def __init__(
        self,
        cache: CacheManager,
        service: SchedulingService | None = None,
    ) -> None:
        """Create the presenter with the shared cache and scheduling service."""
        self._cache = cache
        self._service = service or SchedulingService()

    def generate(self) -> GenerationResult:
        """Run scheduling on cached data and report a display-ready result."""
        try:
            outcome = self._service.run(self._cache, rank_results=False)
        except ValueError as error:
            return GenerationResult(success=False, message=str(error))
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            return GenerationResult(
                success=False,
                message=(
                    "Schedule generation failed unexpectedly: "
                    f"{type(error).__name__}."
                ),
            )

        return self._result_from_full_outcome(outcome)

    def generate_progressive(
        self,
        on_snapshot: Callable[[ProgressiveRankedSnapshot], None] | None = None,
        cancellation_token: Any | None = None,
        options: ProgressiveGenerationOptions | None = None,
    ) -> GenerationResult:
        """Run progressive generation and return a final display result.

        ``on_snapshot`` receives ``PARTIAL`` and terminal snapshots from the
        service.  The returned ``GenerationResult`` is only the final summary the
        existing screen code already knows how to display.
        """
        try:
            final_snapshot = self._service.run_progressive(
                cache=self._cache,
                options=options,
                on_snapshot=on_snapshot,
                cancellation_token=cancellation_token,
            )
        except ValueError as error:
            return GenerationResult(success=False, message=str(error))
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            return GenerationResult(
                success=False,
                message=(
                    "Schedule generation failed unexpectedly: "
                    f"{type(error).__name__}."
                ),
            )

        return self._result_from_progressive_snapshot(final_snapshot)

    @staticmethod
    def _result_from_full_outcome(outcome) -> GenerationResult:
        """Translate ``SchedulingOutcome`` to GUI-facing text."""
        if outcome.schedule_count == 0:
            if outcome.relevant_course_count == 0:
                message = (
                    "No exam courses found for the selected programs. "
                    "Try selecting different programs."
                )
            elif outcome.any_constraint_enabled:
                message = (
                    "No valid exam systems satisfy the current selection "
                    "with the active threshold constraints. Try relaxing a "
                    "threshold constraint, excluding fewer dates, or changing "
                    "programs."
                )
            else:
                message = (
                    "No valid exam systems could be generated for the current "
                    "selection. Try excluding fewer dates or changing programs."
                )
            return GenerationResult(
                success=True,
                message=message,
                schedule_count=0,
                pruned_candidates=outcome.pruned_candidates,
            )

        return GenerationResult(
            success=True,
            message=f"{outcome.schedule_count} exam system(s) generated.",
            schedule_count=outcome.schedule_count,
            displayed_count=outcome.schedule_count,
        )

    @staticmethod
    def _result_from_progressive_snapshot(
        snapshot: ProgressiveRankedSnapshot,
    ) -> GenerationResult:
        """Translate a terminal progressive snapshot to GUI-facing text."""
        if snapshot.state == ProgressiveResultState.CANCELLED:
            return GenerationResult(
                success=False,
                message=snapshot.message,
                schedule_count=snapshot.counters.systems_seen,
                pruned_candidates=snapshot.counters.pruned_candidates,
                displayed_count=snapshot.counters.displayed_count,
            )

        if snapshot.state == ProgressiveResultState.FAILED:
            return GenerationResult(
                success=False,
                message=snapshot.message,
                schedule_count=snapshot.counters.systems_seen,
                pruned_candidates=snapshot.counters.pruned_candidates,
                displayed_count=snapshot.counters.displayed_count,
            )

        if snapshot.counters.systems_seen == 0:
            if snapshot.relevant_course_count == 0:
                message = (
                    "No exam courses found for the selected programs. "
                    "Try selecting different programs."
                )
            else:
                message = (
                    "No valid exam systems could be generated for the current "
                    "selection. Try excluding fewer dates, relaxing threshold "
                    "constraints, or changing programs."
                )
            return GenerationResult(
                success=True,
                message=message,
                schedule_count=0,
                pruned_candidates=snapshot.counters.pruned_candidates,
                displayed_count=0,
            )

        return GenerationResult(
            success=True,
            message=snapshot.message,
            schedule_count=snapshot.counters.systems_seen,
            pruned_candidates=snapshot.counters.pruned_candidates,
            displayed_count=snapshot.counters.displayed_count,
        )
