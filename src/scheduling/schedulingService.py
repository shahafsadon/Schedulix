"""Scheduling service that connects the GUI cache to the Version 1.0 engine
(SCRUM-125), extended to honor Part 3 threshold constraints and ranking
preferences from the cache (SCRUM-164).

Version 1.0 exposes its full pipeline through SchedulixApp.run(), which reads
input files from disk, generates schedules, and writes an output file. The
Version 2.0 GUI already holds its data in memory (inside the CacheManager) and
must not re-read files or write an output file just to display results on
screen.

This service bridges that gap. It takes the data already stored in the cache
(courses, exam periods, selected programs, threshold-constraint settings, and
ranking settings), runs the same core Version 1.0 logic (course filtering +
exam-system generation) without any file I/O, applies the active Part 3
threshold constraints during generation, ranks the results according to the
active ranking preferences, stores everything back into the cache, and
returns it to the caller.

It deliberately reuses the existing CourseFilter, ExamScheduleGenerator,
ScheduleRankingService, and SchedulingSettingsValidator rather than
duplicating any scheduling or validation logic, so the Version 2.0 results
stay identical to Version 1.0 for the same inputs and the same validation
rules apply regardless of which flow (GUI or CLI) triggered generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from application.cache_manager import CacheManager
from application.settings_validator import SchedulingSettingsValidator
from ranking_settings import RankedExamSystem, RankingSettings
from scheduling.courseFilter import CourseFilter
from scheduling.examScheduleGenerator import ExamScheduleGenerator, ExamSystem
from scheduling.scheduleRankingService import ScheduleRankingService


@dataclass(frozen=True)
class SchedulingOutcome:
    """Summary of one scheduling run, returned to the presenter.

    `schedules` is also stored in the cache as a side effect; it is returned
    here too so the caller can react without a second cache read. The counts
    let the UI show a short status line without recomputing anything.

    The three candidate-evaluation counters mirror
    ``ExamScheduleGenerator.SchedulingDiagnostics``. They count individual
    (course, date) placement attempts during the recursive search, not
    complete exam systems — `accepted_candidates` is generally larger than
    `schedule_count`. They are exposed for diagnostics/debugging, but are
    NOT a reliable signal for "a Part 3 threshold constraint caused a
    zero-result run": the always-active base conflict rule
    (SameDateProgramYearConflictConstraint) also contributes to
    `pruned_candidates`, and final-system-only constraints (e.g.
    mandatory_span_days) are not counted at all.

    `any_constraint_enabled` is the field the presenter should use instead to
    decide whether a zero-result message should point at Part 3 constraints
    or at date availability. It reflects whether at least one
    ThresholdConstraintType entry in the active SchedulingConstraintSettings
    is enabled, independent of how many candidates were pruned.
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


class SchedulingService:
    """Runs the Version 1.0 scheduling core on data held in the cache.

    The service is stateless apart from its injected collaborators. All input
    comes from the CacheManager passed to run(), and all output goes back into
    that same cache, keeping the GUI's single source of truth consistent.

    Threshold-constraint settings and ranking settings are read from the
    cache on every run() call, since they may change between runs (e.g. the
    user adjusts a constraint in the settings screen and regenerates).
    Settings are validated through SchedulingSettingsValidator before being
    passed to the generator; invalid settings raise ValueError rather than
    reaching the engine, matching the existing error-handling pattern used by
    the missing-input checks below.
    """

    def __init__(
        self,
        course_filter: CourseFilter | None = None,
        schedule_generator: ExamScheduleGenerator | None = None,
        ranking_service: ScheduleRankingService | None = None,
        ranking_settings: RankingSettings | None = None,
        settings_validator: SchedulingSettingsValidator | None = None,
    ) -> None:
        """Create the service with its scheduling collaborators.

        Args:
            course_filter: reuses the Version 1.0 filter; a default is created
                when none is supplied so application code stays simple.
            schedule_generator: when supplied, this exact generator instance is
                used for every run() call (useful for tests that inject a
                fake/stub generator). When omitted (the normal production
                path), run() builds a fresh ExamScheduleGenerator on each call,
                configured with the constraint settings read from the cache,
                so threshold-constraint changes take effect immediately.
            ranking_service: reuses the Version 1.0 ranking service; defaulted
                the same way.
            ranking_settings: fallback ranking preferences used only if the
                cache itself returns no ranking settings. In normal operation
                CacheManager.get_ranking_settings() always returns a valid
                object (empty priority list by default), so this fallback is
                mainly useful for tests that construct the service directly.
            settings_validator: reuses the shared SCRUM-143 validator;
                defaulted the same way so GUI and CLI flows apply identical
                validation rules.
        """
        # Reuse the real Version 1.0 components unless tests inject their own.
        self._course_filter = course_filter or CourseFilter()
        self._injected_generator = schedule_generator
        self._ranking_service = ranking_service or ScheduleRankingService()
        self._fallback_ranking_settings = ranking_settings or RankingSettings([])
        self._settings_validator = settings_validator or SchedulingSettingsValidator()

    def run(self, cache: CacheManager) -> SchedulingOutcome:
        """Generate exam systems from the cached data and store them back.

        Reads courses, exam periods, selected programs, threshold-constraint
        settings, and ranking settings from the cache. Validates the
        constraint and ranking settings, keeps only the Exam courses belonging
        to the selected programs, generates all valid exam systems under the
        active constraints, ranks them according to the active ranking
        preferences, writes everything back into the cache, and returns a
        summary.

        Raises:
            ValueError: if the cache is missing courses, exam periods, or a
                program selection — i.e. the user reached generation without
                completing the earlier wizard steps — or if the cached
                constraint/ranking settings fail validation.
        """
        courses = cache.get_courses()
        exam_periods = cache.get_exam_periods()
        selected_programs = cache.get_selected_programs()

        # Fail clearly rather than silently producing an empty result: each of
        # these is set by an earlier wizard step, so an empty value means the
        # user (or a bug) skipped a required step.
        if not courses:
            raise ValueError("No courses loaded. Load a courses file first.")
        if not exam_periods:
            raise ValueError("No exam periods loaded. Load a dates file first.")
        if not selected_programs:
            raise ValueError("No programs selected. Select at least one program.")

        # Step 0: read the active Part 3 settings from the cache. CacheManager
        # always returns a usable object (all-disabled constraints / empty
        # ranking list when nothing was ever stored), so these are never None.
        constraint_settings = cache.get_constraint_settings()
        ranking_settings = (
            cache.get_ranking_settings() or self._fallback_ranking_settings
        )

        # Validate before anything reaches the generator. Both halves are
        # checked together so a single call surfaces every problem.
        validation_result = self._settings_validator.validate(
            constraint_settings=constraint_settings,
            ranking_settings=ranking_settings,
        )
        if not validation_result.is_valid:
            raise ValueError(
                "Invalid scheduling settings:\n"
                + "\n".join(validation_result.error_messages)
            )

        # Used by the presenter to decide whether a zero-result run should be
        # explained by "constraints are too strict" or "no date fits". This
        # is independent of the diagnostics counters below, which also count
        # rejections from the always-active base conflict rule and do not
        # count final-system-only constraint rejections (see SchedulingOutcome).
        any_constraint_enabled = any(
            setting.enabled
            for setting in constraint_settings.constraints.values()
        )

        # Step 1: keep only Exam courses that belong to the selected programs.
        # This is the exact same filtering rule used by Version 1.0.
        relevant_courses = self._course_filter.filter_relevant_courses(
            courses,
            selected_programs,
        )

        # Step 2: generate every valid exam-system option (no file I/O here).
        # When a generator was injected (tests), reuse it as-is. Otherwise
        # build a fresh generator configured with the current constraint
        # settings, so threshold-constraint changes take effect on the next
        # run() without needing a new SchedulingService instance.
        generator = self._injected_generator or ExamScheduleGenerator(
            constraint_settings=constraint_settings,
        )
        schedules = generator.generate_exam_systems(
            relevant_courses,
            exam_periods,
        )

        # Step 3: calculate metrics once and rank the wrappers. With empty
        # ranking settings this preserves generation order.
        ranking_outcome = self._ranking_service.rank_generated_schedules(
            schedules,
            ranking_settings,
        )

        # Step 4: store raw and ranked results separately so ranking-only
        # changes never modify the original generated systems.
        cache.set_generated_schedules(schedules)
        cache.set_ranked_schedules(ranking_outcome.ranked_schedules)

        return SchedulingOutcome(
            relevant_course_count=len(relevant_courses),
            schedule_count=len(schedules),
            schedules=schedules,
            ranked_schedules=ranking_outcome.ranked_schedules,
            ranking_seconds=ranking_outcome.elapsed_seconds,
            generated_candidates=generator.diagnostics.generated_candidates,
            accepted_candidates=generator.diagnostics.accepted_candidates,
            pruned_candidates=generator.diagnostics.pruned_candidates,
            any_constraint_enabled=any_constraint_enabled,
        )
