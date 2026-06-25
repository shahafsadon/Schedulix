"""Scheduling service for GUI-owned in-memory data.

The synchronous ``run()`` method is kept for compatibility with the existing
screens/tests.  The progressive ``run_progressive()`` method adds lazy batched
ranking on top of ``ExamScheduleGenerator.iter_exam_systems()`` so the GUI can
show a ranked preview without materializing the full Cartesian product.

Academic-review orientation
---------------------------
This file is the central Version 34 use-case coordinator.  It intentionally
does not implement the low-level schedule-generation algorithm, the metric
calculator, or the GUI widgets.  Its job is to connect those separate parts:

1. read validated state from ``CacheManager``;
2. filter the course list down to the selected programs;
3. create a constraint-aware ``ExamScheduleGenerator``;
4. stream generated systems lazily;
5. rank each generated batch;
6. retain only a bounded Top-N preview; and
7. emit immutable progress snapshots to the GUI.

This separation is important for code review: the file demonstrates the
Service Layer pattern and explains why Version 34 ranking/progressive preview
logic was kept out of the customTkinter screens.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from application.cache_manager import CacheManager
from application.settings_validator import SchedulingSettingsValidator
from ranking_settings import RankedExamSystem, RankingSettings
from scheduling.courseFilter import CourseFilter
from scheduling.batchIterator import GeneratedScheduleBatch, iter_exam_system_batches
from scheduling.examScheduleGenerator import ExamScheduleGenerator, ExamSystem
from scheduling.fallbackScheduleService import FallbackScheduleService
from scheduling.progressiveGeneration import (
    ProgressiveCounters,
    ProgressiveGenerationOptions,
    ProgressiveRankedSnapshot,
    ProgressiveResultState,
)
from scheduling.rankedResultsBuffer import RankedResultsBuffer
from scheduling.scheduleRankingService import ScheduleRankingService


@dataclass(frozen=True)
class SchedulingOutcome:
    """Summary of one scheduling run, returned to the presenter.

    ``schedules`` is also stored in the cache as a side effect; it is returned
    here too so the caller can react without a second cache read. The counts let
    the UI show a short status line without recomputing anything.

    This object belongs to the older full-materialization path.  It is still
    useful for compatibility and tests, but Version 34's preferred GUI path is
    ``ProgressiveRankedSnapshot`` because a snapshot can represent partial
    progress without requiring the complete schedule list.
    """

    relevant_course_count: int
    schedule_count: int
    schedules: list[ExamSystem]
    ranked_schedules: list[RankedExamSystem] = field(default_factory=list)
    ranking_seconds: float = 0.0
    generated_candidates: int = 0
    accepted_candidates: int = 0
    pruned_candidates: int = 0
    any_constraint_enabled: bool = False


@dataclass(frozen=True)
class _PreparedSchedulingInput:
    """Validated and filtered inputs for one scheduling run.

    The service gathers these values once at the beginning of a run so the
    generation code receives a coherent input set: courses, exam periods,
    active constraints, and ranking preferences are all from the same cache
    state.  This avoids scattering validation and cache reads throughout the
    progressive loop.
    """

    relevant_courses: list[Any]
    exam_periods: list[Any]
    constraint_settings: Any
    ranking_settings: RankingSettings
    any_constraint_enabled: bool


class SchedulingService:
    """Runs the scheduling core on data held in ``CacheManager``.

    Responsibility
    --------------
    ``SchedulingService`` is an application service, not a domain algorithm.
    It coordinates the scheduling use case and delegates specialized work to
    collaborators:

    * ``CourseFilter`` decides which courses matter for selected programs.
    * ``ExamScheduleGenerator`` produces valid ``ExamSystem`` objects.
    * ``ScheduleRankingService`` calculates metrics and orders schedules.
    * ``RankedResultsBuffer`` owns Top-N preview retention.
    * ``CacheManager`` persists only durable, final results.

    Side effects are intentionally limited to cache writes at well-defined
    points.  In the progressive flow, partial previews are emitted to callbacks
    but are not persisted as final schedule state.
    """

    def __init__(
        self,
        course_filter: CourseFilter | None = None,
        schedule_generator: ExamScheduleGenerator | None = None,
        ranking_service: ScheduleRankingService | None = None,
        fallback_service: FallbackScheduleService | None = None,
        ranking_settings: RankingSettings | None = None,
        settings_validator: SchedulingSettingsValidator | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        """Create the service with its scheduling collaborators.

        Parameters are injectable so unit tests can replace expensive or
        stateful collaborators with fakes.  This is why the service is easy to
        review independently from the GUI and from the recursive generator.
        """
        self._course_filter = course_filter or CourseFilter()
        self._injected_generator = schedule_generator
        self._ranking_service = ranking_service or ScheduleRankingService()
        self._fallback_service = fallback_service or FallbackScheduleService()
        self._fallback_ranking_settings = ranking_settings or RankingSettings([])
        self._settings_validator = settings_validator or SchedulingSettingsValidator()
        self._clock = clock
        self._run_counter = 0

    def run(self, cache: CacheManager, rank_results: bool = True) -> SchedulingOutcome:
        """Generate all exam systems from cached data and store them back.

        This compatibility path still materializes the full list because older
        callers expect ``SchedulingOutcome.schedules`` to contain every system.
        New GUI preview flows should use ``run_progressive()``.

        Side effects
        ------------
        Writes generated schedules to ``CacheManager`` and, when requested,
        writes ranked schedules as well.  This is safe for the old path because
        the method only returns after full generation completes.
        """
        # Step 1: normalize all cache state into a single prepared input object.
        # This keeps validation, filtering, and settings lookup outside the
        # generator so the generator can focus only on schedule construction.
        prepared = self._prepare_inputs(cache)
        generator = self._create_generator(prepared.constraint_settings)

        # Compatibility path: this deliberately materializes all systems.  The
        # method remains for older screens/tests that expect a complete list,
        # while Version 34's scalable path uses run_progressive().
        schedules = generator.generate_exam_systems(
            prepared.relevant_courses,
            prepared.exam_periods,
        )

        if rank_results and not schedules and self._injected_generator is None:
            fallback = self._fallback_service.generate_best_alternatives(
                prepared.relevant_courses,
                prepared.exam_periods,
                prepared.constraint_settings,
                prepared.ranking_settings,
                display_limit=1,
            )
            ranked_schedules = fallback.ranked_schedules
            schedules = [
                ranked_system.exam_system
                for ranked_system in ranked_schedules
            ]
            ranking_seconds = 0.0
        elif rank_results:
            # Ranking is a separate service because "valid" and "best" are two
            # different questions.  The generator answers validity; this
            # service delegates schedule preference ordering to the ranking
            # layer after generation has completed.
            ranking_outcome = self._ranking_service.rank_generated_schedules(
                schedules,
                prepared.ranking_settings,
            )
            ranked_schedules = ranking_outcome.ranked_schedules
            ranking_seconds = ranking_outcome.elapsed_seconds
        else:
            ranked_schedules = []
            ranking_seconds = 0.0

        cache.set_generated_schedules(schedules)
        if rank_results:
            cache.set_ranked_schedules(ranked_schedules)

        diagnostics = self._diagnostics(generator)
        return SchedulingOutcome(
            relevant_course_count=len(prepared.relevant_courses),
            schedule_count=len(schedules),
            schedules=schedules,
            ranked_schedules=ranked_schedules,
            ranking_seconds=ranking_seconds,
            generated_candidates=diagnostics.generated_candidates,
            accepted_candidates=diagnostics.accepted_candidates,
            pruned_candidates=diagnostics.pruned_candidates,
            any_constraint_enabled=prepared.any_constraint_enabled,
        )

    def run_progressive(
        self,
        cache: CacheManager,
        options: ProgressiveGenerationOptions | None = None,
        on_snapshot: Callable[[ProgressiveRankedSnapshot], None] | None = None,
        cancellation_token: Any | None = None,
    ) -> ProgressiveRankedSnapshot:
        """Generate and rank schedules progressively.

        The method consumes ``ExamScheduleGenerator.iter_exam_systems()`` lazily,
        ranks each completed batch, and keeps only a bounded top-N preview.  It
        does not call the list-returning generator wrapper unless a test double
        lacks the lazy iterator entirely.

        Partial snapshots are delivered through ``on_snapshot``.  The returned
        value is always the terminal snapshot: ``COMPLETE`` or ``CANCELLED``.

        Algorithmic idea
        ----------------
        The method is a streaming pipeline:

        ``lazy generator`` -> ``fixed-size batches`` -> ``rank batch`` ->
        ``merge into Top-N buffer`` -> ``emit immutable snapshot``.

        This avoids the old bottleneck of "generate every schedule, store every
        schedule, then rank every schedule" before the user sees anything.
        """
        # Options control the user-facing responsiveness/memory tradeoff.  A
        # small batch size gives frequent updates; a large batch size reduces
        # callback overhead.  display_limit bounds the ranked preview.
        options = options or ProgressiveGenerationOptions()
        run_id = self._next_run_id()
        ranking_version = run_id
        started_at = self._clock()
        prepared = self._prepare_inputs(cache)
        generator = self._create_generator(prepared.constraint_settings)
        # The buffer is the memory-safety boundary: it retains only the current
        # Top-N schedules rather than the full generated history.
        preview = RankedResultsBuffer(
            ranking_settings=prepared.ranking_settings,
            preview_limit=options.display_limit,
        )

        if self._is_cancelled(cancellation_token):
            # Edge case: cancellation can be requested before the worker enters
            # the generation loop.  Returning a terminal snapshot gives the GUI
            # one consistent code path for all cancellation timings.
            snapshot = self._build_snapshot(
                run_id=run_id,
                state=ProgressiveResultState.CANCELLED,
                preview=preview,
                generator=generator,
                relevant_course_count=len(prepared.relevant_courses),
                ranking_version=ranking_version,
                started_at=started_at,
                message="Schedule generation was cancelled before it started.",
            )
            self._emit(on_snapshot, snapshot)
            return snapshot

        last_emit_at = started_at

        generated_systems = self._iter_exam_systems(
            generator,
            prepared.relevant_courses,
            prepared.exam_periods,
        )
        batches = iter_exam_system_batches(
            generated_systems,
            options.batch_size,
            starting_schedule_id=1,
            should_stop=lambda: self._is_cancelled(cancellation_token),
        )

        # Main progressive loop:
        # 1. pull the next generated batch from the lazy iterator;
        # 2. re-read ranking settings so the GUI can change ranking preference
        #    while generation is active;
        # 3. rank and merge into the bounded preview;
        # 4. optionally emit a throttled PARTIAL snapshot.
        for schedule_batch in batches:
            if schedule_batch.is_empty:
                # Empty batches should not normally occur, but tolerating them
                # keeps the batch iterator contract defensive and avoids
                # emitting meaningless progress updates.
                continue

            latest_settings = cache.get_ranking_settings() or prepared.ranking_settings
            if preview.ranking_settings != latest_settings:
                # Only the schedules still retained in the buffer can be
                # reranked here.  This is the deliberate Top-N memory tradeoff:
                # global reranking under brand-new criteria would require
                # storing all discarded schedules or restarting generation.
                preview.rerank(latest_settings)
                ranking_version += 1

            self._rank_batch_into_preview(
                preview=preview,
                schedule_batch=schedule_batch,
                ranking_settings=latest_settings,
            )

            if self._is_cancelled(cancellation_token):
                # Cancellation after a batch is ranked still returns the latest
                # in-memory preview, but does not persist it as final cache
                # state.  This protects previous valid results from being
                # replaced by an incomplete run.
                return self._finish_progressive_run(
                    cache=cache,
                    options=options,
                    on_snapshot=on_snapshot,
                    run_id=run_id,
                    state=ProgressiveResultState.CANCELLED,
                    preview=preview,
                    generator=generator,
                    relevant_course_count=len(prepared.relevant_courses),
                    ranking_version=ranking_version,
                    started_at=started_at,
                    message=(
                        "Schedule generation was cancelled. Preview results "
                        "were not saved."
                    ),
                )

            now = self._clock()
            if now - last_emit_at >= options.min_update_interval_seconds:
                # Throttling prevents the background worker from flooding the
                # Tk event queue with too many GUI updates on very fast batches.
                snapshot = self._build_snapshot(
                    run_id=run_id,
                    state=ProgressiveResultState.PARTIAL,
                    preview=preview,
                    generator=generator,
                    relevant_course_count=len(prepared.relevant_courses),
                    ranking_version=ranking_version,
                    started_at=started_at,
                    message=self._partial_message(preview, options.display_limit),
                )
                self._emit(on_snapshot, snapshot)
                last_emit_at = now

        if self._is_cancelled(cancellation_token):
            # A second cancellation check after the loop covers cancellation
            # requested between the final batch and terminal completion.
            return self._finish_progressive_run(
                cache=cache,
                options=options,
                on_snapshot=on_snapshot,
                run_id=run_id,
                state=ProgressiveResultState.CANCELLED,
                preview=preview,
                generator=generator,
                relevant_course_count=len(prepared.relevant_courses),
                ranking_version=ranking_version,
                started_at=started_at,
                message=(
                    "Schedule generation was cancelled. Preview results "
                    "were not saved."
                ),
            )

        if preview.systems_seen == 0 and self._injected_generator is None:
            # Strict generation found no schedules that satisfy every enabled
            # constraint.  Version 34 fallback is deliberately conservative:
            # it runs only here, keeps hard red-line constraints enforced, and
            # converts only soft preference violations into penalty metadata.
            fallback = self._fallback_service.generate_best_alternatives(
                prepared.relevant_courses,
                prepared.exam_periods,
                prepared.constraint_settings,
                prepared.ranking_settings,
                display_limit=options.display_limit,
            )
            if fallback.ranked_schedules:
                preview.add_ranked_batch(
                    fallback.ranked_schedules,
                    generated_count=fallback.generated_count,
                    accepted_count=len(fallback.ranked_schedules),
                    processed_count=fallback.generated_count,
                    ranking_seconds=0.0,
                )
                best_fallback = fallback.ranked_schedules[0]
                return self._finish_progressive_run(
                    cache=cache,
                    options=options,
                    on_snapshot=on_snapshot,
                    run_id=run_id,
                    state=ProgressiveResultState.COMPLETE,
                    preview=preview,
                    generator=generator,
                    relevant_course_count=len(prepared.relevant_courses),
                    ranking_version=ranking_version,
                    started_at=started_at,
                    message=self._fallback_message(best_fallback),
                    is_fallback=True,
                    penalty_score=best_fallback.penalty_score,
                    penalty_details=best_fallback.penalty_details,
                )

        return self._finish_progressive_run(
            cache=cache,
            options=options,
            on_snapshot=on_snapshot,
            run_id=run_id,
            state=ProgressiveResultState.COMPLETE,
            preview=preview,
            generator=generator,
            relevant_course_count=len(prepared.relevant_courses),
            ranking_version=ranking_version,
            started_at=started_at,
            message=self._complete_message(preview, options.display_limit),
        )

    # ------------------------------------------------------------------
    # Progressive helpers
    # ------------------------------------------------------------------

    def _prepare_inputs(self, cache: CacheManager) -> _PreparedSchedulingInput:
        """Read, validate, and filter all inputs needed by scheduling.

        Returns
        -------
        _PreparedSchedulingInput
            A coherent bundle of filtered courses, exam periods, constraint
            settings, ranking settings, and a flag describing whether any
            threshold constraint is enabled.

        Raises
        ------
        ValueError
            If required GUI state is missing or if Version 34 settings are
            invalid.  The presenter catches these errors and turns them into
            user-facing messages.
        """
        courses = cache.get_courses()
        exam_periods = cache.get_exam_periods()
        selected_programs = cache.get_selected_programs()

        # These guards fail early with actionable messages.  Without them the
        # generator would fail later with less helpful errors or empty output.
        if not courses:
            raise ValueError("No courses loaded. Load a courses file first.")
        if not exam_periods:
            raise ValueError("No exam periods loaded. Load a dates file first.")
        if not selected_programs:
            raise ValueError("No programs selected. Select at least one program.")

        constraint_settings = cache.get_constraint_settings()
        ranking_settings = (
            cache.get_ranking_settings() or self._fallback_ranking_settings
        )

        validation_result = self._settings_validator.validate(
            constraint_settings=constraint_settings,
            ranking_settings=ranking_settings,
        )
        if not validation_result.is_valid:
            # Validation is kept before filtering/generation so invalid user
            # settings never reach the scheduling domain.
            raise ValueError(
                "Invalid scheduling settings:\n"
                + "\n".join(validation_result.error_messages)
            )

        relevant_courses = self._course_filter.filter_relevant_courses(
            courses,
            selected_programs,
        )
        any_constraint_enabled = any(
            setting.enabled
            for setting in constraint_settings.constraints.values()
        )

        return _PreparedSchedulingInput(
            relevant_courses=relevant_courses,
            exam_periods=exam_periods,
            constraint_settings=constraint_settings,
            ranking_settings=ranking_settings,
            any_constraint_enabled=any_constraint_enabled,
        )

    def _create_generator(self, constraint_settings: Any) -> Any:
        """Create the correct generator for the current run.

        Injected generators support tests; production runs build a fresh
        ``ExamScheduleGenerator`` so each run receives the active constraint
        settings and independent diagnostics counters.
        """
        return self._injected_generator or ExamScheduleGenerator(
            constraint_settings=constraint_settings,
        )

    @staticmethod
    def _iter_exam_systems(
        generator: Any,
        relevant_courses: list[Any],
        exam_periods: list[Any],
    ) -> Iterator[ExamSystem]:
        """Return the lazy exam-system iterator required by progressive mode.

        Progressive generation must never call the list-returning
        ``generate_exam_systems()`` compatibility wrapper. If a test double or
        custom generator lacks ``iter_exam_systems()``, failing fast is safer
        than accidentally materializing every possible schedule in memory.
        """
        iter_method = getattr(generator, "iter_exam_systems", None)
        if not callable(iter_method):
            raise TypeError(
                "Progressive scheduling requires a lazy iter_exam_systems() method."
            )

        yield from iter_method(relevant_courses, exam_periods)

    def _rank_batch_into_preview(
        self,
        preview: RankedResultsBuffer,
        schedule_batch: GeneratedScheduleBatch,
        ranking_settings: RankingSettings,
    ) -> None:
        """Rank one generated batch and merge it into the bounded preview.

        Parameters
        ----------
        preview:
            The mutable Top-N buffer for the current run.
        schedule_batch:
            A generated batch with stable global schedule IDs.
        ranking_settings:
            The ranking settings that should be applied to this batch.

        Side effects
        ------------
        Mutates ``preview`` by updating counters and possibly replacing the
        retained Top-N schedules.  It does not write to cache.
        """
        if schedule_batch.is_empty:
            return

        # The ranking service calculates metrics for this batch and assigns
        # stable IDs starting at schedule_batch.starting_schedule_id.  Stable
        # IDs matter because they keep tie-breaking and GUI labels consistent
        # across progressive batches.
        ranking_outcome = self._ranking_service.rank_generated_batch(
            schedule_batch.schedules,
            ranking_settings,
            starting_schedule_id=schedule_batch.starting_schedule_id,
        )
        # The buffer owns the "current preview + new batch -> rerank -> trim"
        # policy.  Keeping that policy outside the service makes the memory
        # tradeoff explicit and testable.
        preview.add_ranked_batch(
            ranking_outcome.ranked_schedules,
            generated_count=schedule_batch.size,
            accepted_count=schedule_batch.size,
            processed_count=schedule_batch.size,
            ranking_seconds=ranking_outcome.elapsed_seconds,
        )

    def _finish_progressive_run(
        self,
        cache: CacheManager,
        options: ProgressiveGenerationOptions,
        on_snapshot: Callable[[ProgressiveRankedSnapshot], None] | None,
        run_id: int,
        state: ProgressiveResultState,
        preview: RankedResultsBuffer,
        generator: Any,
        relevant_course_count: int,
        ranking_version: int,
        started_at: float,
        message: str,
        is_fallback: bool = False,
        penalty_score: float | None = None,
        penalty_details: tuple[str, ...] = (),
    ) -> ProgressiveRankedSnapshot:
        """Create, optionally persist, emit, and return the terminal snapshot.

        Cache-safety contract (SCRUM-184)
        ----------------------------------
        ``CacheManager`` is written **only** on ``COMPLETE`` with
        ``options.cache_final_preview`` set.  ``PARTIAL`` snapshots emitted
        during the generation loop are intentionally *never* written to cache:
        they are in-memory previews and must not corrupt the permanent session
        store.  ``CANCELLED`` and ``FAILED`` terminal states are also excluded
        so an aborted run leaves the previous (valid) schedules intact on disk.
        """
        # Build the terminal view of the run first.  If we later persist final
        # ranking with the latest ranking settings, the snapshot is replaced
        # with an equivalent copy containing that final ranked order.
        snapshot = self._build_snapshot(
            run_id=run_id,
            state=state,
            preview=preview,
            generator=generator,
            relevant_course_count=relevant_course_count,
            ranking_version=ranking_version,
            started_at=started_at,
            message=message,
            is_fallback=is_fallback,
            penalty_score=penalty_score,
            penalty_details=penalty_details,
        )

        # PARTIAL snapshots are dispatched via on_snapshot() in the main loop
        # and never reach this helper; the guard below is an extra defensive
        # layer ensuring that a future code path cannot accidentally persist a
        # partial preview to the cache.
        if state == ProgressiveResultState.COMPLETE and options.cache_final_preview:
            # Persist only the bounded top-N ranked preview, not the full set.
            # Storing every generated system would undo the lazy-generation
            # optimization that this progressive flow exists to protect.
            latest_settings = cache.get_ranking_settings()
            final_outcome = self._ranking_service.rerank(
                snapshot.ranked_schedules,
                latest_settings,
            )
            final_ranked_schedules = final_outcome.ranked_schedules

            if preview.systems_seen == 0:
                # Even an empty complete run is a meaningful final result: it
                # tells the cache that the current input/settings combination
                # produced no valid schedules.
                cache.store_final_schedule_results([], [], latest_settings)
            else:
                cache.set_ranked_schedules(final_ranked_schedules)

            import dataclasses
            # ``ProgressiveRankedSnapshot`` is frozen, so replacing the ranked
            # list uses dataclasses.replace instead of mutating the object.
            snapshot = dataclasses.replace(snapshot, ranked_schedules=final_ranked_schedules)

        self._emit(on_snapshot, snapshot)
        return snapshot

    def _build_snapshot(
        self,
        run_id: int,
        state: ProgressiveResultState,
        preview: RankedResultsBuffer,
        generator: Any,
        relevant_course_count: int,
        ranking_version: int,
        started_at: float,
        message: str,
        error: str | None = None,
        is_fallback: bool = False,
        penalty_score: float | None = None,
        penalty_details: tuple[str, ...] = (),
    ) -> ProgressiveRankedSnapshot:
        """Build an immutable snapshot from the current mutable state.

        The preview buffer is mutable because it is updated batch-by-batch.
        The GUI receives a frozen snapshot instead, so screen code cannot
        accidentally mutate the service's internal progress state.
        """
        diagnostics = self._diagnostics(generator)
        displayed_count = len(preview.ranked_schedules)
        # Candidate counters describe recursive placement attempts inside the
        # generator.  Schedule counters describe complete ExamSystem objects in
        # the progressive pipeline.  Both are useful during academic review:
        # one explains algorithmic pruning, the other explains user-visible
        # progress.
        counters = ProgressiveCounters(
            systems_seen=preview.systems_seen,
            displayed_count=displayed_count,
            generated_candidates=diagnostics.generated_candidates,
            accepted_candidates=diagnostics.accepted_candidates,
            pruned_candidates=diagnostics.pruned_candidates,
            elapsed_seconds=self._clock() - started_at,
            ranking_seconds=preview.ranking_seconds,
            generated_schedule_count=preview.generated_schedules,
            accepted_schedule_count=preview.accepted_schedules,
            processed_schedule_count=preview.processed_schedules,
            displayed_schedule_count=displayed_count,
        )
        return ProgressiveRankedSnapshot(
            run_id=run_id,
            state=state,
            ranked_schedules=list(preview.ranked_schedules),
            counters=counters,
            relevant_course_count=relevant_course_count,
            ranking_version=ranking_version,
            message=message,
            error=error,
            is_fallback=is_fallback,
            penalty_score=penalty_score,
            penalty_details=penalty_details,
        )

    @staticmethod
    def _emit(
        callback: Callable[[ProgressiveRankedSnapshot], None] | None,
        snapshot: ProgressiveRankedSnapshot,
    ) -> None:
        # The service deliberately knows nothing about Tkinter.  The callback
        # boundary lets the presenter/screen decide how to marshal updates onto
        # the GUI thread.
        if callback is not None:
            callback(snapshot)

    @staticmethod
    def _is_cancelled(cancellation_token: Any | None) -> bool:
        # The token is intentionally duck-typed so tests and different runner
        # implementations only need to expose an ``is_cancelled`` attribute.
        return bool(getattr(cancellation_token, "is_cancelled", False))

    @staticmethod
    def _diagnostics(generator: Any) -> Any:
        """Return generator diagnostics, tolerating simple test doubles."""
        diagnostics = getattr(generator, "diagnostics", None)
        if diagnostics is not None:
            return diagnostics
        # Some tests inject lightweight fakes that do not expose diagnostics.
        # Returning an object with zero-valued fields preserves the presenter
        # contract without forcing every fake to mirror the real generator.
        return type(
            "EmptySchedulingDiagnostics",
            (),
            {
                "generated_candidates": 0,
                "accepted_candidates": 0,
                "pruned_candidates": 0,
            },
        )()

    @staticmethod
    def _partial_message(
        preview: RankedResultsBuffer,
        display_limit: int,
    ) -> str:
        # The wording intentionally says "temporary" so users understand this
        # is a live preview, not the final complete ranked result.
        shown = min(len(preview.ranked_schedules), display_limit)
        return (
            f"Live temporary Top {display_limit:,} preview: showing "
            f"{shown:,} from {preview.systems_seen:,} ranked so far."
        )

    @staticmethod
    def _complete_message(
        preview: RankedResultsBuffer,
        display_limit: int,
    ) -> str:
        # Completion messages distinguish between "all generated schedules fit
        # in the display limit" and "we are showing a bounded final Top-N".
        if preview.systems_seen == 0:
            return "No valid exam systems could be generated."
        shown = min(len(preview.ranked_schedules), display_limit)
        if shown >= preview.systems_seen:
            return (
                f"Final ranking complete for "
                f"{preview.systems_seen:,} generated schedule(s)."
            )
        return (
            f"Final Top {shown:,} ranking complete from "
            f"{preview.systems_seen:,} generated schedule(s)."
        )

    @staticmethod
    def _fallback_message(ranked_system: RankedExamSystem) -> str:
        """Return a clear warning for a best-effort fallback schedule."""
        score = ranked_system.penalty_score
        score_text = "unknown" if score is None else f"{score:g}"
        violation_count = len(ranked_system.penalty_details)
        return (
            "No schedule satisfied all enabled preferences. Showing the best "
            f"hard-valid fallback schedule with penalty score {score_text} "
            f"and {violation_count} soft violation(s)."
        )

    def _next_run_id(self) -> int:
        # Monotonic run IDs let the GUI ignore stale updates if future screens
        # allow overlapping or rapidly restarted progressive runs.
        self._run_counter += 1
        return self._run_counter
