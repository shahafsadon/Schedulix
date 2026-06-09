"""
dateManagementPresenter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Presenter (Invoker) for the Date Management screen (SCRUM-114).

Following the passive MVP pattern, this presenter:
* Holds references to the current ``ExamPeriod``, an ``ExamDateHandler``,
  an optional ``ExamScheduleGenerator``, and a ``CacheManager``.
* Exposes ``on_date_clicked(d)``, ``on_regenerate()``,
  ``on_regenerate_async(...)``, and ``on_edit_period(...)`` as the public
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
from typing import TYPE_CHECKING, Any, Callable

from application.commands import (
    CommandResult,
    EditPeriodCommand,
    RegenerateSchedulesCommand,
    ToggleDateExceptionCommand,
)

if TYPE_CHECKING:
    # Import only for type-checking so that the module stays importable in
    # environments where scheduling or application packages are not on sys.path.
    from application.cache_manager import CacheManager
    from application.async_runner import AsyncScheduleRunner
    from scheduling.examDateHandler import ExamDateHandler
    from scheduling.examScheduleGenerator import ExamScheduleGenerator
    from models import Course, ExamPeriod


class DateManagementPresenter:
    """
    Invoker for date-management commands; drives the Date Management View.

    The presenter is the single point of contact between the passive View and
    the Command objects.  The View calls ``on_date_clicked``,
    ``on_regenerate``, ``on_regenerate_async``, and ``on_edit_period``; the
    presenter instantiates and executes the matching command, then returns a
    ``CommandResult`` or dispatch status for the View to render.

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
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._cache = cache_manager
        self._generator = schedule_generator
        self._courses = courses or []
        self._exam_periods = exam_periods or []
        self._on_change = on_change

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
            self._notify_change()
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

    def on_regenerate_async(
        self,
        runner: "AsyncScheduleRunner",
        on_started: Callable[[], None] | None = None,
        on_complete: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> bool:
        """
        Recompute exam schedules on a background runner.

        The heavy generation work is wrapped in a task closure and delegated to
        ``AsyncScheduleRunner`` so the GUI event loop can remain responsive.
        The task reuses ``RegenerateSchedulesCommand``, keeping cache writes and
        error handling consistent with the synchronous ``on_regenerate`` path.

        Returns
        -------
        bool
            ``True`` when the runner accepted the task, ``False`` when no
            generator exists or when the runner debounced a duplicate request.
        """
        if self._generator is None:
            error = RuntimeError("No schedule generator available; cannot regenerate.")
            if on_error is not None:
                on_error(error)
            return False

        def task() -> Any:
            command = RegenerateSchedulesCommand(
                self._generator,
                self._cache,
                self._courses,
                self._exam_periods,
            )
            result = command.execute()
            self._last_command = None
            if not result.success:
                raise RuntimeError(result.message)
            return result.data

        return runner.run(
            task=task,
            on_started=on_started,
            on_complete=on_complete,
            on_error=on_error,
        )

    def on_edit_period(self, new_start_date: date, new_end_date: date) -> CommandResult:
        """
        Edit the scheduling window (start/end dates) of the active exam period.

        Builds an ``EditPeriodCommand``, executes it, and stores it for
        potential undo when the edit succeeds.  The returned
        ``CommandResult.data`` contains the updated ``list[date]`` of valid
        dates so the View can redraw the calendar immediately.

        Parameters
        ----------
        new_start_date:
            The requested new start date for the period.
        new_end_date:
            The requested new end date for the period.

        Returns
        -------
        CommandResult
            ``success=False`` (period unchanged) if the new range is inverted.
        """
        command = EditPeriodCommand(
            self._exam_period,
            self._date_handler,
            new_start_date,
            new_end_date,
        )
        result = command.execute()
        # Only store the command when the edit was applied, so undo is always
        # meaningful (a rejected inverted-range edit has no state to reverse).
        if result.success:
            self._last_command = command
            self._notify_change()
        return result

    def undo_last(self) -> CommandResult:
        """
        Reverse the most recently executed date-toggle or period-edit command.

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
            self._notify_change()
        return result

    def can_undo(self) -> bool:
        """Return True when the presenter has a successful command to undo."""
        return self._last_command is not None

    def _notify_change(self) -> None:
        """Tell the workflow that the managed period was mutated."""
        if self._on_change is not None:
            self._on_change()

    # ------------------------------------------------------------------
    # Read-only queries for the View
    # ------------------------------------------------------------------

    def current_period(self):
        """
        Return the active ``ExamPeriod`` instance being edited.

        Exposed as a public getter so Views can read period attributes
        (``start_date``, ``end_date``) without accessing a private attribute.

        Returns
        -------
        ExamPeriod
            The exam period currently managed by this presenter.
        """
        return self._exam_period

    def get_valid_dates(self) -> list[date]:
        """Return the current list of valid exam dates for the active period."""
        return self._date_handler.get_valid_dates(self._exam_period)

    def is_excluded(self, d: date) -> bool:
        """Return ``True`` if ``d`` is currently in the blocked-dates list."""
        return d in self._exam_period.excluded_dates

    def count_excluded_inside_window(self) -> int:
        """Return excluded dates currently visible inside the active period."""
        return sum(
            1
            for excluded_date in self._exam_period.excluded_dates
            if self._exam_period.start_date <= excluded_date <= self._exam_period.end_date
        )

    def count_excluded_outside_window(self) -> int:
        """Return stored exclusions that are outside the active period window."""
        return len(self._exam_period.excluded_dates) - self.count_excluded_inside_window()
