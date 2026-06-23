"""Scheduling service for GUI-owned in-memory data.

The synchronous ``run()`` method is kept for compatibility with the existing
screens/tests.  The progressive ``run_progressive()`` method adds lazy batched
ranking on top of ``ExamScheduleGenerator.iter_exam_systems()`` so the GUI can
show a ranked preview without materializing the full Cartesian product.
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
    """Validated and filtered inputs for one scheduling run."""

    relevant_courses: list[Any]
    exam_periods: list[Any]
    constraint_settings: Any
    ranking_settings: RankingSettings
    any_constraint_enabled: bool


class SchedulingService:
    """Runs the scheduling core on data held in ``CacheManager``."""

    def __init__(
        self,
        course_filter: CourseFilter | None = None,
        schedule_generator: ExamScheduleGenerator | None = None,
        ranking_service: ScheduleRankingService | None = None,
        ranking_settings: RankingSettings | None = None,
        settings_validator: SchedulingSettingsValidator | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        """Create the service with its scheduling collaborators."""
        self._course_filter = course_filter or CourseFilter()
        self._injected_generator = schedule_generator
        self._ranking_service = ranking_service or ScheduleRankingService()
        self._fallback_ranking_settings = ranking_settings or RankingSettings([])
        self._settings_validator = settings_validator or SchedulingSettingsValidator()
        self._clock = clock
        self._run_counter = 0

    def run(self, cache: CacheManager) -> SchedulingOutcome:
        """Generate all exam systems from cached data and store them back.

        This compatibility path still materializes the full list because older
        callers expect ``SchedulingOutcome.schedules`` to contain every system.
        New GUI preview flows should use ``run_progressive()``.
        """
        prepared = self._prepare_inputs(cache)
        generator = self._create_generator(prepared.constraint_settings)

        schedules = generator.generate_exam_systems(
            prepared.relevant_courses,
            prepared.exam_periods,
        )

        ranking_outcome = self._ranking_service.rank_generated_schedules(
            schedules,
            prepared.ranking_settings,
        )

        cache.set_generated_schedules(schedules)
        cache.set_ranked_schedules(ranking_outcome.ranked_schedules)

        diagnostics = self._diagnostics(generator)
        return SchedulingOutcome(
            relevant_course_count=len(prepared.relevant_courses),
            schedule_count=len(schedules),
            schedules=schedules,
            ranked_schedules=ranking_outcome.ranked_schedules,
            ranking_seconds=ranking_outcome.elapsed_seconds,
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
        """
        options = options or ProgressiveGenerationOptions()
        run_id = self._next_run_id()
        ranking_version = run_id
        started_at = self._clock()
        prepared = self._prepare_inputs(cache)
        generator = self._create_generator(prepared.constraint_settings)
        preview = RankedResultsBuffer(
            ranking_settings=prepared.ranking_settings,
            preview_limit=options.display_limit,
        )

        if self._is_cancelled(cancellation_token):
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

        for schedule_batch in batches:
            if schedule_batch.is_empty:
                continue

            latest_settings = cache.get_ranking_settings() or prepared.ranking_settings
            if preview.ranking_settings != latest_settings:
                preview.rerank(latest_settings)
                ranking_version += 1

            self._rank_batch_into_preview(
                preview=preview,
                schedule_batch=schedule_batch,
                ranking_settings=latest_settings,
            )

            if self._is_cancelled(cancellation_token):
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
        """Read, validate, and filter all inputs needed by scheduling."""
        courses = cache.get_courses()
        exam_periods = cache.get_exam_periods()
        selected_programs = cache.get_selected_programs()

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
        """Create the correct generator for the current run."""
        return self._injected_generator or ExamScheduleGenerator(
            constraint_settings=constraint_settings,
        )

    @staticmethod
    def _iter_exam_systems(
        generator: Any,
        relevant_courses: list[Any],
        exam_periods: list[Any],
    ) -> Iterator[ExamSystem]:
        """Use the lazy generator when available, with a test-double fallback."""
        iter_method = getattr(generator, "iter_exam_systems", None)
        if callable(iter_method):
            yield from iter_method(relevant_courses, exam_periods)
            return

        # Compatibility fallback for old fakes.  Production ExamScheduleGenerator
        # always exposes iter_exam_systems(), so this should not run in real GUI
        # generation.
        yield from generator.generate_exam_systems(relevant_courses, exam_periods)

    def _rank_batch_into_preview(
        self,
        preview: RankedResultsBuffer,
        schedule_batch: GeneratedScheduleBatch,
        ranking_settings: RankingSettings,
    ) -> None:
        """Rank one generated batch and merge it into the bounded preview."""
        if schedule_batch.is_empty:
            return

        ranking_outcome = self._ranking_service.rank_generated_batch(
            schedule_batch.schedules,
            ranking_settings,
            starting_schedule_id=schedule_batch.starting_schedule_id,
        )
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
        snapshot = self._build_snapshot(
            run_id=run_id,
            state=state,
            preview=preview,
            generator=generator,
            relevant_course_count=relevant_course_count,
            ranking_version=ranking_version,
            started_at=started_at,
            message=message,
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
            final_outcome = self._ranking_service.rerank(snapshot.ranked_schedules, latest_settings)
            final_ranked_schedules = final_outcome.ranked_schedules

            cache.store_final_schedule_results(
                [r.exam_system for r in final_ranked_schedules],
                final_ranked_schedules,
                latest_settings
            )

            import dataclasses
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
    ) -> ProgressiveRankedSnapshot:
        """Build an immutable snapshot from the current mutable state."""
        diagnostics = self._diagnostics(generator)
        displayed_count = len(preview.ranked_schedules)
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
        )

    @staticmethod
    def _emit(
        callback: Callable[[ProgressiveRankedSnapshot], None] | None,
        snapshot: ProgressiveRankedSnapshot,
    ) -> None:
        if callback is not None:
            callback(snapshot)

    @staticmethod
    def _is_cancelled(cancellation_token: Any | None) -> bool:
        return bool(getattr(cancellation_token, "is_cancelled", False))

    @staticmethod
    def _diagnostics(generator: Any) -> Any:
        """Return generator diagnostics, tolerating simple test doubles."""
        diagnostics = getattr(generator, "diagnostics", None)
        if diagnostics is not None:
            return diagnostics
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
        shown = min(len(preview.ranked_schedules), display_limit)
        return (
            f"Preview: showing top {shown:,} from "
            f"{preview.systems_seen:,} generated so far."
        )

    @staticmethod
    def _complete_message(
        preview: RankedResultsBuffer,
        display_limit: int,
    ) -> str:
        if preview.systems_seen == 0:
            return "No valid exam systems could be generated."
        shown = min(len(preview.ranked_schedules), display_limit)
        return (
            f"Complete: showing top {shown:,} from "
            f"{preview.systems_seen:,} generated schedule(s)."
        )

    def _next_run_id(self) -> int:
        self._run_counter += 1
        return self._run_counter
