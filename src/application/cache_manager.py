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

No existing Version 1.0 files are imported or modified by this module.
"""

import pickle
from pathlib import Path

from models import Course, ExamPeriod
from ranking_settings import RankedExamSystem
from scheduling.examScheduleGenerator import ExamSystem


# ---------------------------------------------------------------------------
# Internal persistence helpers
# ---------------------------------------------------------------------------

# _SENTINEL is stored inside the pickle so we can detect a corrupted or
# incompatible file and fall back to a clean state gracefully.
_SENTINEL = "CacheManager_v1"


class _CacheState:
    """
    Plain data container that is serialised to and from disk.

    Keeping the state in its own class means the pickle payload is self-
    contained and does not pull in any CacheManager behaviour.
    """

    def __init__(self) -> None:
        self.sentinel: str = _SENTINEL
        self.courses: list[Course] = []
        self.exam_periods: list[ExamPeriod] = []
        self.selected_programs: list[str] = []
        self.generated_schedules: list[ExamSystem] = []
        self.ranked_schedules: list[RankedExamSystem] = []


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
    * Persist the complete state to ``internal_data.pkl`` after every update.
    * Reload state from ``internal_data.pkl`` on creation so data survives
      application restarts.

    Usage
    -----
    Instantiate once at the application entry point and pass the single
    instance to every presenter or screen that needs it::

        cache = CacheManager()           # loads from disk if file exists
        cache.set_courses(courses)       # persists immediately
        cache.get_courses()              # returns the in-RAM list

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
        as empty lists. If the file exists but is unreadable or was written
        by an incompatible version, the manager silently starts with an empty
        state (the damaged file is left untouched for manual inspection).
        """
        self._state: _CacheState = self._load_from_disk()

    def _load_from_disk(self) -> _CacheState:
        """
        Attempt to deserialise state from the pickle file.

        Returns a fresh _CacheState if the file does not exist or cannot be
        read.
        """
        pkl_path = self.__class__._PKL_PATH  # respects subclass overrides

        if not pkl_path.exists():
            return _CacheState()

        try:
            with pkl_path.open("rb") as fh:
                loaded = pickle.load(fh)
            # Validate that the payload was written by a compatible version.
            if isinstance(loaded, _CacheState) and loaded.sentinel == _SENTINEL:
                self._ensure_current_state_shape(loaded)
                return loaded
        except Exception:
            # Covers PickleError, EOFError, AttributeError, and any other
            # deserialisation problem. Fall back to clean state.
            pass

        return _CacheState()

    @staticmethod
    def _ensure_current_state_shape(state: _CacheState) -> None:
        """
        Add fields introduced after older pickle files were written.

        Pickle restores the saved instance attributes exactly, so an old cache
        can be a valid _CacheState while still missing newer fields.
        """
        if not hasattr(state, "ranked_schedules"):
            state.ranked_schedules = []

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
        self._state.courses = list(courses)
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

        Parameters
        ----------
        schedules:
            The list of ``ExamSystem`` objects produced by the scheduling
            engine after the user triggers generation.
        """
        self._state.generated_schedules = list(schedules)
        self._state.ranked_schedules = []
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
        self._persist()

    def get_ranked_schedules(self) -> list[RankedExamSystem]:
        """Return cached ranked schedules (empty list if not calculated yet)."""
        return self._state.ranked_schedules

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """
        Reset all state to empty and delete the persistence file.

        Use this when the user starts a new session or when a test needs to
        guarantee a clean slate. After this call all getters return empty
        lists and no pickle file exists on disk.
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
        self._state.courses.extend(courses)
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
        Clear only the generated-schedules field and persist the updated state.

        All other fields are left untouched.
        """
        self._state.generated_schedules = []
        self._state.ranked_schedules = []
        self._persist()

    def invalidate_ranked_schedules(self) -> None:
        """
        Clear only the ranked-schedules field and persist the updated state.

        This is useful when ranking preferences change while generated systems
        remain valid but the previous display order should be discarded.
        """
        self._state.ranked_schedules = []
        self._persist()
