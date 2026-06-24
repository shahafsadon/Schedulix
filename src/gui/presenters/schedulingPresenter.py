"""Presenter for triggering schedule generation.

The presenter keeps GUI code out of the scheduling service.  ``generate()`` is
kept for the existing full-materialization flow, while ``generate_progressive``
uses the service's lazy batched ranking path and forwards snapshots to the view.

Academic-review orientation
---------------------------
This presenter is the GUI boundary for Version 34 generation.  It deliberately
does not know how schedules are generated, how metrics are calculated, or how
Top-N previews are retained.  Its responsibility is to translate between:

* GUI-friendly ``GenerationResult`` objects; and
* service/domain objects such as ``SchedulingOutcome`` and
  ``ProgressiveRankedSnapshot``.

That separation keeps customTkinter screens passive and makes generation
behavior testable without launching the desktop interface.
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
    """Display-ready outcome of a generation attempt.

    The presenter returns this simplified object to screens so GUI code does
    not need to know the full internal shape of ``SchedulingOutcome`` or
    ``ProgressiveRankedSnapshot``.  It contains only the values the screen needs
    for status labels and navigation decisions.
    """

    success: bool
    message: str
    schedule_count: int = 0
    pruned_candidates: int = 0
    displayed_count: int = 0
    partial: bool = False


class SchedulingPresenter:
    """Drives the schedule-generation step of the wizard.

    Responsibility
    --------------
    ``SchedulingPresenter`` is an MVP presenter.  The Date Management screen
    calls it when the user asks to generate schedules.  The presenter delegates
    the actual use case to ``SchedulingService`` and converts service results
    into a small GUI-facing result object.
    """

    def __init__(
        self,
        cache: CacheManager,
        service: SchedulingService | None = None,
    ) -> None:
        """Create the presenter with the shared cache and scheduling service.

        Dependency injection lets tests pass a fake service, and keeps the
        presenter independent of concrete scheduling implementation details.
        """
        self._cache = cache
        self._service = service or SchedulingService()

    def generate(self) -> GenerationResult:
        """Run scheduling on cached data and report a display-ready result.

        This method preserves the older full-materialization flow.  It is kept
        so existing screens/tests can still request a complete generation run,
        but the Version 34 responsive path is ``generate_progressive()``.
        """
        try:
            # ``rank_results=False`` keeps this legacy path focused on raw
            # generation. Ranking/progressive preview are handled by the newer
            # method below.
            outcome = self._service.run(self._cache, rank_results=False)
        except ValueError as error:
            # Expected user/data errors are returned as friendly messages rather
            # than escaping into the GUI event handler.
            return GenerationResult(success=False, message=str(error))
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            # The GUI should not crash on unexpected service errors.  The
            # detailed exception type is kept in the message for debugging while
            # avoiding a large traceback in the user interface.
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

        Parameters
        ----------
        on_snapshot:
            Optional callback used by the screen to display live ranked preview
            updates.
        cancellation_token:
            Cooperative cancellation flag supplied by the async runner.
        options:
            Batch size, display limit, update throttle, and cache behavior.

        Side effects
        ------------
        The service may persist final results to cache.  Partial snapshots are
        only forwarded to the callback.
        """
        try:
            # The presenter does not inspect or mutate progressive internals.
            # It simply passes through the callback and converts the terminal
            # snapshot into the existing GUI result shape.
            final_snapshot = self._service.run_progressive(
                cache=self._cache,
                options=options,
                on_snapshot=on_snapshot,
                cancellation_token=cancellation_token,
            )
        except ValueError as error:
            # Validation/missing-data errors are expected during normal GUI use
            # and should be shown as actionable text.
            return GenerationResult(success=False, message=str(error))
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            # Catch-all protection keeps background scheduling failures from
            # breaking the GUI event loop.
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
        """Translate ``SchedulingOutcome`` to GUI-facing text.

        The service returns detailed domain/use-case information.  This helper
        chooses the message that best explains the result to a user.
        """
        if outcome.schedule_count == 0:
            if outcome.relevant_course_count == 0:
                # No relevant exam courses means generation did not fail; the
                # selected programs simply do not produce schedulable exams.
                message = (
                    "No exam courses found for the selected programs. "
                    "Try selecting different programs."
                )
            elif outcome.any_constraint_enabled:
                # When constraints are enabled, zero schedules is often caused
                # by thresholds that are too strict for the selected data.
                message = (
                    "No valid exam systems satisfy the current selection "
                    "with the active threshold constraints. Try relaxing a "
                    "threshold constraint, excluding fewer dates, or changing "
                    "programs."
                )
            else:
                # With no extra constraints, the user likely needs to adjust
                # dates or program selection.
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
        """Translate a terminal progressive snapshot to GUI-facing text.

        Only terminal snapshots reach this helper as final return values from
        ``generate_progressive``.  Partial snapshots are consumed by the live
        preview callback while generation is running.
        """
        if snapshot.state == ProgressiveResultState.CANCELLED:
            # Cancellation is treated as unsuccessful from the user's point of
            # view because no new final schedule set should replace the previous
            # cache state.
            return GenerationResult(
                success=False,
                message=snapshot.message,
                schedule_count=snapshot.counters.systems_seen,
                pruned_candidates=snapshot.counters.pruned_candidates,
                displayed_count=snapshot.counters.displayed_count,
            )

        if snapshot.state == ProgressiveResultState.FAILED:
            # The state is modeled explicitly even though the service currently
            # surfaces most errors through exceptions.  Keeping the branch makes
            # the presenter robust to future service implementations.
            return GenerationResult(
                success=False,
                message=snapshot.message,
                schedule_count=snapshot.counters.systems_seen,
                pruned_candidates=snapshot.counters.pruned_candidates,
                displayed_count=snapshot.counters.displayed_count,
            )

        if snapshot.counters.systems_seen == 0:
            if snapshot.relevant_course_count == 0:
                # Distinguish "nothing to schedule" from "constraints/dates
                # made all schedules invalid" so the user knows what to change.
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
