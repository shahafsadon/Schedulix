"""Presenter for triggering schedule generation (SCRUM-125).

After SCRUM-184 this presenter also acts as the orchestration hub for
smart invalidation and cache persistence:

* ``generate()`` — runs the generation engine and, on success, writes a
  COMPLETE ``ProgressiveRankedSnapshot`` to the cache (schedules + ranking).
  Only COMPLETE snapshots reach the cache; PARTIAL states stay in-memory.

* ``rerank_cached()`` — re-sorts the already-cached schedule list using a
  new ``RankingSettings`` and re-saves it without touching the engine.
  This is the "ranking-only change" fast path: no regeneration required.

* ``invalidate_for_threshold_change()`` — clears the schedule cache and
  resets the ranking so that the next ``generate()`` call starts fresh.
  This is the "threshold constraint change" slow path.

Following the MVP pattern this class contains no customTkinter code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from application.cache_manager import CacheManager
from scheduling.progressiveSnapshot import ProgressiveRankedSnapshot, SnapshotState
from scheduling.rankingSettings import RankingSettings
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
    """Drives the schedule-generation step of the wizard.

    This presenter is the single point of truth for schedule caching.  All
    writes to ``cache.set_generated_schedules()`` and
    ``cache.set_ranking_settings()`` go through this class so the PARTIAL /
    COMPLETE invariant is enforced in one place.
    """

    def __init__(
        self,
        cache: CacheManager,
        service: SchedulingService | None = None,
        initial_ranking: RankingSettings | None = None,
    ) -> None:
        """Create the presenter with the shared cache and a scheduling service.

        Args:
            cache: the single application CacheManager holding the loaded data
                and receiving the generated schedules (Dependency Injection).
            service: the scheduling service to run; a default is created when
                none is supplied, while tests can inject a fake.
            initial_ranking: the ``RankingSettings`` to apply when generation
                finishes.  Defaults to the no-op (generation order) when not
                supplied.  Pass the value loaded from the cache on app startup
                so the previous session's ordering is restored.
        """
        self._cache = cache
        self._service = service or SchedulingService()
        # The active ranking.  Updated by apply_ranking() and rerank_cached().
        self._ranking: RankingSettings = (
            initial_ranking if initial_ranking is not None else RankingSettings.default()
        )
        # In-flight partial snapshot; None when no generation is running.
        self._partial_snapshot: ProgressiveRankedSnapshot | None = None

    # ------------------------------------------------------------------
    # Public: ranking
    # ------------------------------------------------------------------

    @property
    def ranking(self) -> RankingSettings:
        """Return the currently active ranking settings."""
        return self._ranking

    def rerank_cached(self, settings: RankingSettings) -> bool:
        """Re-sort the cached schedule list and persist the new ordering.

        This is the **fast path** for a ranking-only change: the generation
        engine is never called.  The existing schedule list is loaded from the
        cache, sorted with ``settings.sort_key``, and written back alongside
        the new ``settings``.

        Parameters
        ----------
        settings:
            The new ranking specification to apply.

        Returns
        -------
        bool
            ``True`` if there were cached schedules to re-sort.
            ``False`` if the cache was empty (nothing to do).
        """
        schedules = self._cache.get_generated_schedules()
        if not schedules:
            self._ranking = settings
            return False

        snapshot = ProgressiveRankedSnapshot.complete(schedules, settings)
        # with_ranking() returns a new COMPLETE snapshot with the sorted list.
        ranked = snapshot.with_ranking(settings)
        # INVARIANT: only write COMPLETE snapshots to the cache.
        assert ranked.is_complete, "rerank_cached must only produce COMPLETE snapshots"
        self._cache.set_generated_schedules(ranked.schedules)
        self._cache.set_ranking_settings(ranked.ranking_settings)
        self._ranking = settings
        return True

    def invalidate_for_threshold_change(self) -> None:
        """Clear the cached schedules and ranking when threshold constraints change.

        After this call the cache holds no schedules and the ranking reverts to
        the no-op default.  The caller must trigger a new ``generate()`` run
        to repopulate the cache.
        """
        self._cache.invalidate_generated_schedules()
        self._cache.invalidate_ranking_settings()
        self._ranking = RankingSettings.default()
        self._partial_snapshot = None

    # ------------------------------------------------------------------
    # Public: generation
    # ------------------------------------------------------------------

    def generate(self) -> GenerationResult:
        """Run scheduling on cached data and report a display-ready result."""
        try:
            outcome = self._service.run(self._cache)
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

        On success, a ``ProgressiveRankedSnapshot`` with ``COMPLETE`` state is
        built, the current ``self._ranking`` is applied to sort the schedules,
        and both the sorted schedules and the settings are written to the cache.

        PARTIAL snapshots are kept in ``self._partial_snapshot`` during the run
        (intended for future progressive streaming) but are **never** written to
        the cache.

        Translates the service outcome into user-facing text. Missing inputs
        (raised as ValueError by the service) become a friendly failure result
        rather than an exception, so the View can simply show the message.
        """
        try:
            final_snapshot = self._service.run_progressive(
                cache=self._cache,
                options=options,
                on_snapshot=on_snapshot,
                cancellation_token=cancellation_token,
            )
        except ValueError as error:
            # Expected, user-facing problem (e.g. a wizard step was skipped).
            return GenerationResult(success=False, message=str(error))
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            return GenerationResult(
                success=False,
                message=(
                    "Schedule generation failed unexpectedly: "
                    f"{type(error).__name__}."
                ),
            )

        # A valid run that yields zero systems is not an error.
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

        # Build a COMPLETE snapshot and apply the active ranking before caching.
        # The service already wrote the unranked list to the cache inside
        # SchedulingService.run(); we overwrite it now with the ranked version.
        snapshot = ProgressiveRankedSnapshot.complete(outcome.schedules, self._ranking)
        if not self._ranking.is_noop():
            snapshot = snapshot.with_ranking(self._ranking)

        # INVARIANT: only COMPLETE snapshots reach the cache.
        assert snapshot.is_complete, "generate() must only persist COMPLETE snapshots"
        self._cache.set_generated_schedules(snapshot.schedules)
        self._cache.set_ranking_settings(snapshot.ranking_settings)

        # Clear any leftover partial snapshot from a previous interrupted run.
        self._partial_snapshot = None

        return GenerationResult(
            success=True,
            message=f"{outcome.schedule_count} exam system(s) generated.",
            schedule_count=outcome.schedule_count,
            displayed_count=len(outcome.ranked_schedules),
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
