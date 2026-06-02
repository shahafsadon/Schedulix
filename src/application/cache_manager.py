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
                return loaded
        except Exception:
            # Covers PickleError, EOFError, AttributeError, and any other
            # deserialisation problem. Fall back to clean state.
            pass

        return _CacheState()

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
        self._persist()

    def get_generated_schedules(self) -> list[ExamSystem]:
        """Return the generated schedules (empty list if none generated yet)."""
        return self._state.generated_schedules

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
