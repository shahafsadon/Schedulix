"""
dateManagementPresenter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Presenter (Invoker) for the Date Management screen (SCRUM-114).

Following the passive MVP pattern, this presenter:
* Holds references to the current ``ExamPeriod``, an ``ExamDateHandler``,
  an optional ``ExamScheduleGenerator``, and a ``CacheManager``.
* Exposes ``on_date_clicked(d)`` and ``on_regenerate()`` as the public
  interface for the passive View to call on user interaction.
* Instantiates the appropriate ``Command`` objects, executes them, and
  keeps the most recently executed command for one-step undo support.

No ``customtkinter`` imports — this class is fully unit-testable without
launching a display.  All dependencies are injected via the constructor,
in line with the DI rules in Section 2.2 of the design document.

No Version 1.0 source files are modified by this module.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from application.commands import (
    CommandResult,
    RegenerateSchedulesCommand,
    ToggleDateExceptionCommand,
)

if TYPE_CHECKING:
    # Import only for type-checking so that the module stays importable in
    # environments where scheduling or application packages are not on sys.path.
    from application.cache_manager import CacheManager
    from scheduling.examDateHandler import ExamDateHandler
    from scheduling.examScheduleGenerator import ExamScheduleGenerator
    from models import Course, ExamPeriod


class DateManagementPresenter:
    """
    Invoker for date-management commands; drives the Date Management View.

    The presenter is the single point of contact between the passive View and
    the Command objects.  The View calls ``on_date_clicked`` and
    ``on_regenerate``; the presenter instantiates and executes the matching
    command, then returns a ``CommandResult`` for the View to render.

    Parameters
    ----------
    exam_period:
        The ``ExamPeriod`` that the user is currently editing.
    date_handler:
        An ``ExamDateHandler`` instance used by date commands to compute the
        updated valid-date list after each mutation.
    cache_manager:
        The application ``CacheManager`` that stores generated schedules.
    schedule_generator:
        An ``ExamScheduleGenerator`` used by the regeneration command.
        If ``None``, ``on_regenerate`` returns a failure result.
    courses:
        The course list passed to the regeneration command.
    exam_periods:
        All exam periods passed to the regeneration command (usually the full
        list stored in the cache, not just the one being edited).
    """

    def __init__(
        self,
        exam_period,
        date_handler,
        cache_manager,
        schedule_generator=None,
        courses: list | None = None,
        exam_periods: list | None = None,
    ) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._cache = cache_manager
        self._generator = schedule_generator
        self._courses = courses or []
        self._exam_periods = exam_periods or []

        # Keeps the last executed command so undo_last() can reverse it.
        self._last_command: object | None = None

    # ------------------------------------------------------------------
    # Public interface called by the passive View
    # ------------------------------------------------------------------

    def on_date_clicked(self, clicked_date: date) -> CommandResult:
        """
        Toggle the excluded/active state of ``clicked_date``.

        Builds a ``ToggleDateExceptionCommand``, executes it, and stores it
        for potential undo.  The returned ``CommandResult.data`` contains the
        updated ``list[date]`` of valid dates so the View can redraw the
        calendar immediately.

        Parameters
        ----------
        clicked_date:
            The calendar date the user clicked on.

        Returns
        -------
        CommandResult
            Result carrying ``data=list[date]`` (updated valid-date list).
        """
        command = ToggleDateExceptionCommand(
            self._exam_period,
            self._date_handler,
            clicked_date,
        )
        result = command.execute()
        # Only store the command when execution succeeded, so undo is always
        # meaningful (a failed toggle has no state to reverse).
        if result.success:
            self._last_command = command
        return result

    def on_regenerate(self) -> CommandResult:
        """
        Recompute exam schedules and persist them to the cache.

        Builds a ``RegenerateSchedulesCommand`` and executes it.  The
        returned ``CommandResult.data`` is the new ``list[ExamSystem]``.

        Returns
        -------
        CommandResult
            ``success=False`` if no schedule generator was injected.
        """
        if self._generator is None:
            return CommandResult(
                success=False,
                message="No schedule generator available; cannot regenerate.",
            )

        command = RegenerateSchedulesCommand(
            self._generator,
            self._cache,
            self._courses,
            self._exam_periods,
        )
        result = command.execute()
        # Regeneration does not support undo; clear last command.
        self._last_command = None
        return result

    def undo_last(self) -> CommandResult:
        """
        Reverse the most recently executed date-toggle command.

        Returns
        -------
        CommandResult
            ``success=False`` if no undoable command is available.
        """
        if self._last_command is None:
            return CommandResult(
                success=False,
                message="Nothing to undo.",
            )
        result = self._last_command.undo()
        if result.success:
            # Consuming the command: a second undo would be a no-op anyway.
            self._last_command = None
        return result

    # ------------------------------------------------------------------
    # Read-only queries for the View
    # ------------------------------------------------------------------

    def get_valid_dates(self) -> list[date]:
        """Return the current list of valid exam dates for the active period."""
        return self._date_handler.get_valid_dates(self._exam_period)

    def is_excluded(self, d: date) -> bool:
        """Return ``True`` if ``d`` is currently in the blocked-dates list."""
        return d in self._exam_period.excluded_dates
