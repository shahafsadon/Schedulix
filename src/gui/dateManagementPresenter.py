"""
dateManagementPresenter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Presenter (Invoker) for the Date Management screen (SCRUM-114 / SCRUM-115).

This presenter handles two concerns:
1. **Synchronous date-toggle commands** (SCRUM-114): ``on_date_clicked`` and
   ``undo_last``.
2. **Async schedule regeneration** (SCRUM-115): ``on_regenerate_async``, which
   delegates to an ``AsyncScheduleRunner`` so the GUI thread is never blocked.

No ``customtkinter`` imports — this class is fully unit-testable without a
display.  All dependencies are injected via the constructor.

No Version 1.0 source files are modified by this module.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from application.commands import (
    CommandResult,
    RegenerateSchedulesCommand,
    ToggleDateExceptionCommand,
)


class DateManagementPresenter:
    """
    Invoker for date-management commands; drives the Date Management View.

    Synchronous API (SCRUM-114)
    ---------------------------
    * ``on_date_clicked(d)`` — toggles excluded/active state of a calendar date.
    * ``undo_last()`` — reverses the most recent toggle.
    * ``get_valid_dates()`` — current valid exam dates for the active period.
    * ``is_excluded(d)`` — checks whether a date is currently blocked.

    Asynchronous API (SCRUM-115)
    ----------------------------
    * ``on_regenerate_async(runner, ...)`` — offloads schedule generation to a
      background thread via the injected ``AsyncScheduleRunner``.  Returns
      ``False`` (debounced) if a generation is already in progress.

    Parameters
    ----------
    exam_period:
        The ``ExamPeriod`` the user is currently editing.
    date_handler:
        ``ExamDateHandler`` used by date commands to recompute valid dates.
    cache_manager:
        The application ``CacheManager`` that stores generated schedules.
    schedule_generator:
        ``ExamScheduleGenerator`` used by the regeneration command.
        If ``None``, both ``on_regenerate`` and ``on_regenerate_async`` return
        a failure result.
    courses:
        Course list passed to the regeneration command.
    exam_periods:
        All exam periods passed to the regeneration command.
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

        # The last successfully executed toggle command, kept for undo support.
        self._last_command: object | None = None

    # ------------------------------------------------------------------
    # Synchronous public interface (SCRUM-114)
    # ------------------------------------------------------------------

    def on_date_clicked(self, clicked_date: date) -> CommandResult:
        """
        Toggle the excluded/active state of ``clicked_date``.

        The returned ``CommandResult.data`` contains the refreshed
        ``list[date]`` of valid dates so the View can redraw the calendar.
        """
        command = ToggleDateExceptionCommand(
            self._exam_period,
            self._date_handler,
            clicked_date,
        )
        result = command.execute()
        if result.success:
            self._last_command = command
        return result

    def undo_last(self) -> CommandResult:
        """
        Reverse the most recently executed date-toggle command.

        Returns ``success=False`` if no undoable command is available.
        """
        if self._last_command is None:
            return CommandResult(success=False, message="Nothing to undo.")
        result = self._last_command.undo()
        if result.success:
            self._last_command = None
        return result

    def get_valid_dates(self) -> list[date]:
        """Return the current list of valid exam dates for the active period."""
        return self._date_handler.get_valid_dates(self._exam_period)

    def is_excluded(self, d: date) -> bool:
        """Return ``True`` if ``d`` is currently in the blocked-dates list."""
        return d in self._exam_period.excluded_dates

    # ------------------------------------------------------------------
    # Asynchronous public interface (SCRUM-115)
    # ------------------------------------------------------------------

    def on_regenerate_async(
        self,
        runner,
        on_started:  Callable[[], None]          | None = None,
        on_complete: Callable[[Any], None]       | None = None,
        on_error:    Callable[[Exception], None] | None = None,
    ) -> bool:
        """
        Offload schedule generation to a background thread via ``runner``.

        The caller (typically the View) is responsible for wrapping
        ``on_complete`` and ``on_error`` in ``widget.after(0, ...)`` so that
        any subsequent widget updates happen on the Tkinter main thread.

        Parameters
        ----------
        runner:
            An ``AsyncScheduleRunner`` instance that manages the thread.
        on_started:
            Optional callback fired synchronously (on the calling thread)
            before the background thread starts — ideal for showing a spinner.
        on_complete:
            Optional callback fired from the background thread with the
            resulting ``list[ExamSystem]``.  The runner also persists the
            result to ``CacheManager`` before firing this callback.
        on_error:
            Optional callback fired from the background thread when generation
            raises an exception.

        Returns
        -------
        bool
            ``True`` if the task was dispatched.
            ``False`` if a task is already in progress (debounced).
            Returns ``False`` immediately if no schedule generator was injected.
        """
        if self._generator is None:
            if on_error is not None:
                on_error(
                    RuntimeError("No schedule generator available; cannot regenerate.")
                )
            return False

        # Build a zero-argument task closure that the runner will call from
        # the background thread.  The cache write happens inside the closure
        # so the result is persisted before on_complete fires.
        def _task():
            schedules = self._generator.generate_exam_systems(
                self._courses, self._exam_periods
            )
            self._cache.set_generated_schedules(schedules)
            return schedules

        return runner.run(
            task=_task,
            on_started=on_started,
            on_complete=on_complete,
            on_error=on_error,
        )
