"""
cache_manager.py
~~~~~~~~~~~~~~~~
Standalone application state manager for the Schedulix GUI layer.

CacheManager is a plain object (not a Singleton) that is instantiated once at
the application root and injected into presenters or screens as a constructor
parameter (Dependency Injection pattern).

State is persisted automatically via Python's ``pickle`` library using a
write-through strategy: every mutating operation updates the in-RAM state first
and immediately overwrites ``internal_data.pkl`` so that the file is always
consistent with the in-memory view.

On initialisation the manager reloads any previously-saved state from the file,
allowing the GUI to survive restarts without re-uploading datasets.

Version history
---------------
v1 / v2  – courses, exam_periods, selected_programs, generated_schedules,
            ranked_schedules.  Sentinel was the string ``"CacheManager_v1"``.

v3 (SCRUM-144) – adds ``constraint_settings`` and ``ranking_settings`` to the
            persisted state.  Smart invalidation rules now guarantee that
            threshold changes wipe generated schedules while ranking-only
            changes do not.  Old v2 pickle files are loaded gracefully: the
            two new fields are injected with their defaults so no crash occurs.

No existing Version 1.0 files are imported or modified by this module.
"""

import logging
import pickle
from pathlib import Path

from constraint_settings import SchedulingConstraintSettings
from models import Course, ExamPeriod, ProgramEnrollment
from ranking_settings import RankedExamSystem, RankingSettings
from scheduling.examScheduleGenerator import ExamSystem


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal persistence helpers
# ---------------------------------------------------------------------------

# _SENTINEL is stored inside the pickle so we can detect a corrupted or
# incompatible file and fall back to a clean state gracefully.
# Bumped to "CacheManager_v3" in SCRUM-144 to distinguish the new schema.
_SENTINEL = "CacheManager_v3"

# The v2 sentinel value is retained so that old files can be identified and
# up-migrated rather than silently discarded.
_SENTINEL_V2 = "CacheManager_v1"

# Generated schedule lists can become very large and make restart sluggish or
# impossible after an interrupted run. The GUI now persists final ranked Top-N
# previews instead of the full generated universe, so caches above this limit
# are treated as unsafe derived data and invalidated during load.
MAX_PERSISTED_GENERATED_SCHEDULES = 500
MAX_PERSISTED_RANKED_SCHEDULES = 500


class _CacheState:
    """
    Plain data container that is serialised to and from disk.

    Keeping the state in its own class means the pickle payload is self-
    contained and does not pull in any CacheManager behaviour.

    v3 additions (SCRUM-144)
    ------------------------
    * ``constraint_settings`` – the active ``SchedulingConstraintSettings``.
      Defaults to all-disabled via ``SchedulingConstraintSettings.default_configuration()``.
    * ``ranking_settings``    – the active ``RankingSettings``.
      Defaults to an empty priority list.
    """

    def __init__(self) -> None:
        self.sentinel: str = _SENTINEL
        self.courses: list[Course] = []
        self.exam_periods: list[ExamPeriod] = []
        self.selected_programs: list[str] = []
        self.generated_schedules: list[ExamSystem] = []
        self.ranked_schedules: list[RankedExamSystem] = []
        self.result_mode: str = "unranked_generated"
        # v3 fields — SCRUM-144
        self.constraint_settings: SchedulingConstraintSettings = (
            SchedulingConstraintSettings.default_configuration()
        )
        self.ranking_settings: RankingSettings = RankingSettings(priority_list=[])


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------


class CacheManager:
    """
    Tracks the application state for the Schedulix GUI session.

    Responsibilities
    ----------------
    * Store uploaded datasets (courses, exam periods / dates).
    * Store the user-selected study program numbers.
    * Store the generated exam schedules produced by the scheduling engine.
    * Store the active ``SchedulingConstraintSettings`` and ``RankingSettings``.
    * Persist the complete state to ``internal_data.pkl`` after every update.
    * Reload state from ``internal_data.pkl`` on creation so data survives
      application restarts.

    Smart cache invalidation (SCRUM-144)
    -------------------------------------
    * ``set_constraint_settings`` – stores new settings and **invalidates**
      generated schedules and ranked schedules, because a threshold change
      means previously-generated schedules are stale.
    * ``set_ranking_settings``    – stores new settings and **invalidates only
      ranked schedules**, because a ranking-order change does not affect
      whether the generated systems themselves are valid.

    Backward compatibility
    ----------------------
    Old v2 pickle files (sentinel ``"CacheManager_v1"``) are up-migrated on
    load: missing v3 fields are injected with their defaults.  The sentinel is
    updated to ``"CacheManager_v3"`` the next time any mutating operation
    persists the state.

    Usage
    -----
    Instantiate once at the application entry point and pass the single
    instance to every presenter or screen that needs it::

        cache = CacheManager()                    # loads from disk if file exists
        cache.set_courses(courses)                # persists immediately
        cache.set_constraint_settings(settings)   # also invalidates schedules
        cache.get_courses()                       # returns the in-RAM list

    Design constraints
    ------------------
    * NOT a Singleton — create with ``CacheManager()``.
    * Overriding ``_PKL_PATH`` before construction lets unit tests redirect
      persistence to a temporary directory without touching the real file.
    """

    # Class-level path so unit tests can redirect it to a tmp directory by
    # reassigning CacheManager._PKL_PATH before instantiating.
    _PKL_PATH: Path = Path(__file__).parent / "internal_data.pkl"

    # ------------------------------------------------------------------
    # Construction / persistence
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        """
        Create the manager and reload any previously persisted state.

        If ``internal_data.pkl`` does not exist yet, all state fields start
        as empty/default values. If the file exists but is unreadable or was
        written by an incompatible version, the manager logs the reason and
        starts with a clean state (the damaged file is left untouched for
        manual inspection).

        Old v2 files are up-migrated transparently; the application will not
        crash when the two new v3 settings fields are absent in the pickle.
        """
        self._state: _CacheState = self._load_from_disk()

    def _load_from_disk(self) -> _CacheState:
        """
        Attempt to deserialise state from the pickle file.

        Handles four cases:
        * File absent                → fresh _CacheState.
        * File is a current v3 file → returned after shape-check.
        * File is an old v2 file    → up-migrated with v3 defaults.
        * Any other error           → fresh _CacheState (fail-safe).
        """
        pkl_path = self.__class__._PKL_PATH  # respects subclass overrides

        if not pkl_path.exists():
            return _CacheState()

        try:
            with pkl_path.open("rb") as fh:
                loaded = pickle.load(fh)

            if not isinstance(loaded, _CacheState):
                logger.warning(
                    "Ignoring cache file %s: expected _CacheState, got %s.",
                    pkl_path,
                    type(loaded).__name__,
                )
                return _CacheState()

            # Current v3 file.
            if loaded.sentinel == _SENTINEL:
                self._ensure_current_state_shape(loaded)
                self._repair_duplicated_courses(loaded, pkl_path)
                self._invalidate_unsafe_derived_state(loaded, pkl_path)
                return loaded

            # Old v2 file: sentinel is the legacy string.
            if loaded.sentinel == _SENTINEL_V2:
                self._migrate_v2_to_v3(loaded)
                self._repair_duplicated_courses(loaded, pkl_path)
                self._invalidate_unsafe_derived_state(loaded, pkl_path)
                return loaded

            logger.warning(
                "Ignoring cache file %s: unsupported sentinel %r.",
                pkl_path,
                getattr(loaded, "sentinel", None),
            )

        except (pickle.PickleError, EOFError, AttributeError, ImportError, ValueError, TypeError) as error:
            logger.warning(
                "Ignoring unreadable cache file %s: %s.",
                pkl_path,
                error,
            )
        except OSError as error:
            logger.warning(
                "Could not read cache file %s: %s.",
                pkl_path,
                error,
            )

        return _CacheState()

    @staticmethod
    def _ensure_current_state_shape(state: _CacheState) -> None:
        """
        Add fields introduced after older pickle files were written.

        Pickle restores the saved instance attributes exactly, so an old cache
        can be a valid _CacheState while still missing newer fields.  This
        method is the definitive list of all backward-compatibility patches.
        """
        # ranked_schedules was added between the original sentinel and v3.
        if not hasattr(state, "ranked_schedules"):
            state.ranked_schedules = []
        if not hasattr(state, "result_mode"):
            state.result_mode = "unranked_generated"
        # v3 new fields — SCRUM-144
        if not hasattr(state, "constraint_settings"):
            state.constraint_settings = (
                SchedulingConstraintSettings.default_configuration()
            )
        if not hasattr(state, "ranking_settings"):
            state.ranking_settings = RankingSettings(priority_list=[])

    @classmethod
    def _repair_duplicated_courses(
        cls,
        state: _CacheState,
        pkl_path: Path,
    ) -> None:
        """Repair exact duplicate courses saved by older GUI sessions.

        A repeated append upload used to save the same course more than once.
        Exact duplicates are safe to merge. Conflicting records are kept so
        the scheduling validation can report the bad input instead of losing
        information silently.
        """
        try:
            normalized_courses = cls._normalize_courses(state.courses)
        except ValueError as error:
            logger.warning(
                "Could not normalize courses in cache file %s: %s.",
                pkl_path,
                error,
            )
            return

        if normalized_courses == state.courses:
            return

        state.courses = normalized_courses
        try:
            with pkl_path.open("wb") as fh:
                pickle.dump(state, fh)
        except OSError as error:
            logger.warning(
                "Could not persist repaired courses to cache file %s: %s.",
                pkl_path,
                error,
            )

    @staticmethod
    def _normalize_courses(courses: list[Course]) -> list[Course]:
        """Return one merged course record for every course number.

        Repeated uploads may contain the same course with the same basic
        details. Their program rows are combined, while conflicting course
        details are rejected because the correct record is unknown.
        """
        normalized: dict[str, Course] = {}
        enrollment_keys: dict[str, set[tuple[str, int, str, str]]] = {}

        for course in courses:
            existing = normalized.get(course.course_number)
            if existing is None:
                copied_programs = list(course.programs)
                normalized[course.course_number] = Course(
                    name=course.name,
                    course_number=course.course_number,
                    instructor=course.instructor,
                    programs=copied_programs,
                    evaluation_type=course.evaluation_type,
                )
                enrollment_keys[course.course_number] = {
                    CacheManager._enrollment_key(program)
                    for program in copied_programs
                }
                continue

            if not CacheManager._same_course_details(existing, course):
                raise ValueError(
                    "Course number "
                    f"{course.course_number!r} has conflicting course details."
                )

            known_keys = enrollment_keys[course.course_number]
            for program in course.programs:
                key = CacheManager._enrollment_key(program)
                if key not in known_keys:
                    existing.programs.append(program)
                    known_keys.add(key)

        return list(normalized.values())

    @staticmethod
    def _same_course_details(first: Course, second: Course) -> bool:
        """Return True when two records describe the same course."""
        return (
            first.name == second.name
            and first.instructor == second.instructor
            and first.evaluation_type == second.evaluation_type
        )

    @staticmethod
    def _enrollment_key(program: ProgramEnrollment) -> tuple[str, int, str, str]:
        """Return the fields that make one program enrollment unique."""
        return (
            program.program_number,
            program.year,
            program.semester,
            program.status,
        )

    @staticmethod
    def _invalidate_unsafe_derived_state(
        state: _CacheState,
        pkl_path: Path,
    ) -> None:
        """Discard stale/heavy generated results loaded from disk.

        Uploaded input data and user settings are durable session state.
        Generated/ranked schedules are derived state and may be huge or
        incomplete after an interrupted background run, so they are validated
        separately and cleared when unsafe.
        """
        generated = getattr(state, "generated_schedules", [])
        ranked = getattr(state, "ranked_schedules", [])

        unsafe_reason: str | None = None
        if not isinstance(generated, list):
            unsafe_reason = "generated_schedules is not a list"
        elif not isinstance(ranked, list):
            unsafe_reason = "ranked_schedules is not a list"
        elif len(generated) > MAX_PERSISTED_GENERATED_SCHEDULES:
            unsafe_reason = (
                "generated_schedules contains "
                f"{len(generated)} items, above the safe persisted limit "
                f"of {MAX_PERSISTED_GENERATED_SCHEDULES}"
            )
        elif len(ranked) > MAX_PERSISTED_RANKED_SCHEDULES:
            unsafe_reason = (
                "ranked_schedules contains "
                f"{len(ranked)} items, above the safe persisted limit "
                f"of {MAX_PERSISTED_RANKED_SCHEDULES}"
            )

        if unsafe_reason is None:
            return

        logger.warning(
            "Invalidating unsafe generated cache data from %s: %s.",
            pkl_path,
            unsafe_reason,
        )
        state.generated_schedules = []
        state.ranked_schedules = []
        state.result_mode = "unranked_generated"

    @staticmethod
    def _migrate_v2_to_v3(state: _CacheState) -> None:
        """
        Up-migrate a v2 ``_CacheState`` to the v3 schema in place.

        Updates the sentinel string and injects any missing v3 fields with
        their safe defaults.  The caller is responsible for persisting the
        migrated state on the next write.
        """
        state.sentinel = _SENTINEL

        if not hasattr(state, "ranked_schedules"):
            state.ranked_schedules = []
        if not hasattr(state, "result_mode"):
            state.result_mode = "unranked_generated"
        if not hasattr(state, "constraint_settings"):
            state.constraint_settings = (
                SchedulingConstraintSettings.default_configuration()
            )
        if not hasattr(state, "ranking_settings"):
            state.ranking_settings = RankingSettings(priority_list=[])

    def _persist(self) -> None:
        """
        Write the current in-RAM state to disk (write-through).

        Called automatically at the end of every setter so the file is always
        in sync with memory.
        """
        pkl_path = self.__class__._PKL_PATH
        with pkl_path.open("wb") as fh:
            pickle.dump(self._state, fh)

    # ------------------------------------------------------------------
    # Courses
    # ------------------------------------------------------------------

    def set_courses(self, courses: list[Course]) -> None:
        """
        Replace the stored courses list and persist to disk.

        Parameters
        ----------
        courses:
            The full list of ``Course`` objects parsed from an uploaded file.
        """
        self._state.courses = self._normalize_courses(courses)
        self._persist()

    def get_courses(self) -> list[Course]:
        """Return the currently stored courses (empty list if none set)."""
        return self._state.courses

    # ------------------------------------------------------------------
    # Exam periods
    # ------------------------------------------------------------------

    def set_exam_periods(self, exam_periods: list[ExamPeriod]) -> None:
        """
        Replace the stored exam-periods list and persist to disk.

        Parameters
        ----------
        exam_periods:
            The full list of ``ExamPeriod`` objects parsed from an uploaded
            dates file.
        """
        self._state.exam_periods = list(exam_periods)
        self._persist()

    def get_exam_periods(self) -> list[ExamPeriod]:
        """Return the currently stored exam periods (empty list if none set)."""
        return self._state.exam_periods

    # ------------------------------------------------------------------
    # Selected programs
    # ------------------------------------------------------------------

    def set_selected_programs(self, programs: list[str]) -> None:
        """
        Replace the selected-programs list and persist to disk.

        Parameters
        ----------
        programs:
            Program numbers chosen by the user, e.g. ``["83101", "83108"]``.
        """
        self._state.selected_programs = list(programs)
        self._persist()

    def get_selected_programs(self) -> list[str]:
        """Return the currently selected program numbers (empty list if none)."""
        return self._state.selected_programs

    # ------------------------------------------------------------------
    # Generated schedules
    # ------------------------------------------------------------------

    def set_generated_schedules(self, schedules: list[ExamSystem]) -> None:
        """
        Replace the generated-schedules list and persist to disk.

        Clears ranked schedules as a side effect because the new set of raw
        systems has not yet been sorted by any ranking criteria.

        Parameters
        ----------
        schedules:
            The list of ``ExamSystem`` objects produced by the scheduling
            engine after the user triggers generation.
        """
        self._state.generated_schedules = list(schedules)
        self._state.ranked_schedules = []
        self._state.result_mode = "unranked_generated"
        self._persist()

    def get_generated_schedules(self) -> list[ExamSystem]:
        """Return the generated schedules (empty list if none generated yet)."""
        return self._state.generated_schedules

    # ------------------------------------------------------------------
    # Ranked schedules
    # ------------------------------------------------------------------

    def set_ranked_schedules(
        self,
        schedules: list[RankedExamSystem],
    ) -> None:
        """
        Replace the ranked-schedules list and persist to disk.

        Ranked schedules wrap the original generated ExamSystem objects with
        cached metrics and the current display order.  They are intentionally
        stored separately from generated_schedules so ranking-only changes do
        not mutate the generator output.
        """
        self._state.ranked_schedules = list(schedules)
        self._state.result_mode = "final_ranked"
        self._persist()

    def get_ranked_schedules(self) -> list[RankedExamSystem]:
        """Return cached ranked schedules (empty list if not calculated yet)."""
        return self._state.ranked_schedules

    def get_result_mode(self) -> str:
        """Return the explicit display mode for cached schedule results."""
        return getattr(self._state, "result_mode", "unranked_generated")

    # ------------------------------------------------------------------
    # Constraint settings  (v3 — SCRUM-144)
    # ------------------------------------------------------------------

    def set_constraint_settings(
        self,
        settings: SchedulingConstraintSettings,
    ) -> None:
        """
        Store new constraint settings and invalidate all derived schedule data.

        **Smart invalidation rule:** a threshold change means the previously-
        generated schedules were produced under different constraints and are
        now stale.  Both ``generated_schedules`` and ``ranked_schedules`` are
        cleared.

        Parameters
        ----------
        settings:
            The new ``SchedulingConstraintSettings`` to activate.
        """
        self._state.constraint_settings = settings
        # Threshold change → stale generated schedules must be wiped.
        self._state.generated_schedules = []
        self._state.ranked_schedules = []
        self._state.result_mode = "unranked_generated"
        self._persist()

    def get_constraint_settings(self) -> SchedulingConstraintSettings:
        """
        Return the active constraint settings.

        Always returns a valid object: if no settings were ever stored (e.g.
        after loading a v2 cache file), the all-disabled default configuration
        is returned.
        """
        return self._state.constraint_settings

    # ------------------------------------------------------------------
    # Ranking settings  (v3 — SCRUM-144)
    # ------------------------------------------------------------------

    def set_ranking_settings(self, settings: RankingSettings) -> None:
        """
        Store new ranking settings and invalidate only the ranked schedules.

        **Smart invalidation rule:** a ranking-order change does not affect
        whether the generated ``ExamSystem`` objects themselves are valid.
        Only the cached ranking result (``ranked_schedules``) is stale and
        must be cleared so the next display pass re-sorts correctly.

        Generated schedules are intentionally left untouched.

        Parameters
        ----------
        settings:
            The new ``RankingSettings`` (priority list) to activate.
        """
        self._state.ranking_settings = settings
        # Ranking-only change → only the ranked view is stale.
        self._state.ranked_schedules = []
        self._state.result_mode = "unranked_generated"
        self._persist()

    def get_ranking_settings(self) -> RankingSettings:
        """
        Return the active ranking settings.

        Always returns a valid object: if no settings were stored (e.g. after
        loading a v2 cache file), an empty-priority-list ``RankingSettings``
        is returned.
        """
        return self._state.ranking_settings

    # ------------------------------------------------------------------
    # Atomic Multi-save  (SCRUM-184)
    # ------------------------------------------------------------------

    def store_final_schedule_results(
        self,
        generated_schedules: list[ExamSystem],
        ranked_schedules: list[RankedExamSystem],
        ranking_settings: RankingSettings,
    ) -> None:
        """
        Atomically save the final results from a progressive scheduling run.
        """
        self._state.generated_schedules = list(generated_schedules)
        self._state.ranked_schedules = list(ranked_schedules)
        self._state.ranking_settings = ranking_settings
        self._state.result_mode = "final_ranked"
        self._persist()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """
        Reset all state to defaults and delete the persistence file.

        Use this when the user starts a new session or when a test needs to
        guarantee a clean slate. After this call all getters return empty
        lists / default settings and no pickle file exists on disk.
        """
        self._state = _CacheState()
        pkl_path = self.__class__._PKL_PATH
        if pkl_path.exists():
            pkl_path.unlink()

    # ------------------------------------------------------------------
    # Incremental additions (add_*)
    # ------------------------------------------------------------------
    # These methods append new items to an existing list rather than
    # replacing it.  The write-through contract is the same as set_*:
    # the pkl file is overwritten immediately after every call.

    def add_courses(self, courses: list[Course]) -> None:
        """
        Append new courses to the existing list and persist to disk.

        Use this for incremental uploads where the user adds more courses
        without discarding the ones already loaded.  To replace everything
        at once, use :meth:`set_courses` instead.

        Parameters
        ----------
        courses:
            The additional ``Course`` objects to append.
        """
        self._state.courses = self._normalize_courses(
            [*self._state.courses, *courses]
        )
        self._persist()

    def add_exam_periods(self, exam_periods: list[ExamPeriod]) -> None:
        """
        Append new exam periods to the existing list and persist to disk.

        Parameters
        ----------
        exam_periods:
            The additional ``ExamPeriod`` objects to append.
        """
        self._state.exam_periods.extend(exam_periods)
        self._persist()

    def add_selected_programs(self, programs: list[str]) -> None:
        """
        Append new program numbers to the selected list and persist to disk.

        Duplicate program numbers are silently ignored so the list always
        contains each program number at most once.

        Parameters
        ----------
        programs:
            Program numbers to add, e.g. ``["83101", "83108"]``.
        """
        existing = set(self._state.selected_programs)
        for program in programs:
            if program not in existing:
                self._state.selected_programs.append(program)
                existing.add(program)
        self._persist()

    def add_generated_schedules(self, schedules: list[ExamSystem]) -> None:
        """
        Append new exam systems to the generated-schedules list and persist.

        Parameters
        ----------
        schedules:
            The additional ``ExamSystem`` objects to append.
        """
        self._state.generated_schedules.extend(schedules)
        self._state.ranked_schedules = []
        self._state.result_mode = "unranked_generated"
        self._persist()

    # ------------------------------------------------------------------
    # Per-field cache invalidation (invalidate_*)
    # ------------------------------------------------------------------
    # These methods zero out a single field in RAM and immediately write
    # the updated (partial) state to disk.  Other fields are left intact.
    # This is a surgical alternative to clear(), which wipes everything
    # and deletes the file.  Use invalidate_* when the user re-uploads
    # only one dataset without wanting to discard the rest.

    def invalidate_courses(self) -> None:
        """
        Clear only the courses field and persist the updated state to disk.

        All other fields (exam periods, selected programs, generated
        schedules) are left untouched.
        """
        self._state.courses = []
        self._persist()

    def invalidate_exam_periods(self) -> None:
        """
        Clear only the exam-periods field and persist the updated state.

        All other fields are left untouched.
        """
        self._state.exam_periods = []
        self._persist()

    def invalidate_selected_programs(self) -> None:
        """
        Clear only the selected-programs field and persist the updated state.

        All other fields are left untouched.
        """
        self._state.selected_programs = []
        self._persist()

    def invalidate_generated_schedules(self) -> None:
        """
        Clear generated schedules and ranked schedules, then persist.

        Ranked schedules are always invalidated together with generated
        schedules because they are derived data: once the source list is
        empty, the previously-sorted view is meaningless.
        """
        self._state.generated_schedules = []
        self._state.ranked_schedules = []
        self._state.result_mode = "unranked_generated"
        self._persist()

    def invalidate_ranked_schedules(self) -> None:
        """
        Clear only the ranked-schedules field and persist the updated state.

        This is useful when ranking preferences change while generated systems
        remain valid but the previous display order should be discarded.
        """
        self._state.ranked_schedules = []
        self._state.result_mode = "unranked_generated"
        self._persist()
