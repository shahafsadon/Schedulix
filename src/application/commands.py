"""
commands.py
~~~~~~~~~~~
Command pattern infrastructure for the Schedulix GUI layer (SCRUM-114).

Design overview
---------------
Each user action on the calendar (excluding a date, re-activating it, or
requesting a full schedule regeneration) is wrapped inside a ``Command``
object.  This fully decouples the passive Views from the underlying domain
logic:

* The **receiver** that commands mutate is ``ExamPeriod`` — the only mutable
  domain object involved.  ``ExamDateHandler`` is stateless and is used as a
  *tool* to recompute the valid-date list after each mutation.
* Commands are instantiated by the Presenter (the Invoker) with all their
  dependencies injected via constructor arguments — no Singleton references.
* ``undo()`` is supported on every command that mutates state, enabling the
  Presenter to offer a one-step revert.

No Version 1.0 source files are modified by this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from constraint_settings import SchedulingConstraintSettings
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.manualScheduleEditor import ManualScheduleEditor


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandResult:
    """
    Lightweight value object returned by every command execution.

    Attributes
    ----------
    success:
        ``True`` when the command completed without errors.
    message:
        Human-readable summary (used by the View for status feedback).
    data:
        Optional payload — for date commands this is the updated
        ``list[date]`` of valid dates; for regeneration it is the new
        ``list[ExamSystem]``.
    """

    success: bool
    message: str = ""
    data: Any = None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class Command(ABC):
    """
    Abstract base class for all GUI commands.

    Every concrete command must implement ``execute()``.  Commands that mutate
    state should also implement ``undo()`` so the Presenter can offer a
    one-step revert; the default implementation returns a failure result with
    an informative message.
    """

    @abstractmethod
    def execute(self) -> CommandResult:
        """
        Perform the action this command represents.

        Returns
        -------
        CommandResult
            A result object describing success/failure and carrying optional
            payload data (e.g. the refreshed valid-date list).
        """
        ...

    def undo(self) -> CommandResult:
        """
        Reverse the effect of the most recent ``execute()`` call.

        The default implementation returns a failure result.  Subclasses that
        mutate state should override this method to restore the previous state.
        """
        return CommandResult(
            success=False,
            message=f"{self.__class__.__name__} does not support undo.",
        )


# ---------------------------------------------------------------------------
# Date-mutation commands
# ---------------------------------------------------------------------------

class ExcludeDateCommand(Command):
    """
    Mark one date as blocked (excluded) within an exam period.

    Adding the date to ``exam_period.excluded_dates`` prevents the
    ``ExamDateHandler`` from returning it as a valid exam date.  The result's
    ``data`` field contains the refreshed valid-date list so the View can
    redraw the calendar without making a separate query.

    Supports ``undo()``: removes the date from ``excluded_dates`` again.

    Parameters
    ----------
    exam_period:
        The ``ExamPeriod`` whose blocked-date list will be updated.
    date_handler:
        An ``ExamDateHandler`` instance used to recompute valid dates.
    target_date:
        The calendar date to block.
    """

    def __init__(self, exam_period, date_handler, target_date: date) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._target_date = target_date
        # Track whether execute() actually added the date so undo() is safe.
        self._did_add: bool = False

    def execute(self) -> CommandResult:
        """
        Append ``target_date`` to ``exam_period.excluded_dates`` if absent.

        Returns
        -------
        CommandResult
            ``success=True`` with updated valid-date list in ``data``.
            If the date is already excluded, ``success=True`` is still
            returned (idempotent) and no duplicate is added.
        """
        if self._target_date not in self._exam_period.excluded_dates:
            self._exam_period.excluded_dates.append(self._target_date)
            self._did_add = True

        valid_dates = self._date_handler.get_valid_dates(self._exam_period)
        return CommandResult(
            success=True,
            message=f"{self._target_date} excluded from exam period.",
            data=valid_dates,
        )

    def undo(self) -> CommandResult:
        """
        Remove ``target_date`` from ``exam_period.excluded_dates``.

        Only performs the removal if ``execute()`` actually added the date,
        ensuring undo is a clean inverse with no side-effects.
        """
        if self._did_add and self._target_date in self._exam_period.excluded_dates:
            self._exam_period.excluded_dates.remove(self._target_date)
            self._did_add = False

        valid_dates = self._date_handler.get_valid_dates(self._exam_period)
        return CommandResult(
            success=True,
            message=f"Exclusion of {self._target_date} reversed.",
            data=valid_dates,
        )


class ActivateDateCommand(Command):
    """
    Re-activate a previously blocked date within an exam period.

    Removes the date from ``exam_period.excluded_dates`` so the
    ``ExamDateHandler`` will include it in future valid-date queries.

    Supports ``undo()``: adds the date back to ``excluded_dates``.

    Parameters
    ----------
    exam_period:
        The ``ExamPeriod`` whose blocked-date list will be updated.
    date_handler:
        An ``ExamDateHandler`` instance used to recompute valid dates.
    target_date:
        The calendar date to unblock.
    """

    def __init__(self, exam_period, date_handler, target_date: date) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._target_date = target_date
        self._did_remove: bool = False

    def execute(self) -> CommandResult:
        """
        Remove ``target_date`` from ``exam_period.excluded_dates`` if present.

        Returns
        -------
        CommandResult
            ``success=True`` with updated valid-date list in ``data``.
            If the date was not excluded, the call is a no-op and still
            returns ``success=True``.
        """
        if self._target_date in self._exam_period.excluded_dates:
            self._exam_period.excluded_dates.remove(self._target_date)
            self._did_remove = True

        valid_dates = self._date_handler.get_valid_dates(self._exam_period)
        return CommandResult(
            success=True,
            message=f"{self._target_date} re-activated in exam period.",
            data=valid_dates,
        )

    def undo(self) -> CommandResult:
        """
        Re-exclude ``target_date`` in ``exam_period.excluded_dates``.

        Only performs the addition if ``execute()`` actually removed the date.
        """
        if self._did_remove and self._target_date not in self._exam_period.excluded_dates:
            self._exam_period.excluded_dates.append(self._target_date)
            self._did_remove = False

        valid_dates = self._date_handler.get_valid_dates(self._exam_period)
        return CommandResult(
            success=True,
            message=f"Re-activation of {self._target_date} reversed.",
            data=valid_dates,
        )


class ToggleDateExceptionCommand(Command):
    """
    Toggle the excluded/active state of a calendar date.

    Inspects the current state of ``exam_period.excluded_dates`` and
    delegates to ``ExcludeDateCommand`` (if active) or
    ``ActivateDateCommand`` (if excluded).  ``undo()`` reverses the
    toggle by calling the delegate's ``undo()``.

    This is the primary command used by the Date Management Presenter in
    response to a calendar-cell click.

    Parameters
    ----------
    exam_period:
        The ``ExamPeriod`` whose blocked-date list will be toggled.
    date_handler:
        An ``ExamDateHandler`` instance used to recompute valid dates.
    target_date:
        The calendar date to toggle.
    """

    def __init__(self, exam_period, date_handler, target_date: date) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._target_date = target_date
        # Resolved at execute-time so the correct delegate handles undo too.
        self._delegate: Command | None = None

    def execute(self) -> CommandResult:
        """
        Exclude the date if it is currently active; activate it if excluded.

        Returns
        -------
        CommandResult
            Result from the underlying delegate command.
        """
        if self._target_date in self._exam_period.excluded_dates:
            self._delegate = ActivateDateCommand(
                self._exam_period, self._date_handler, self._target_date
            )
        else:
            self._delegate = ExcludeDateCommand(
                self._exam_period, self._date_handler, self._target_date
            )
        return self._delegate.execute()

    def undo(self) -> CommandResult:
        """
        Reverse the most recent toggle by delegating to the sub-command's undo.

        Returns a failure result if ``execute()`` was never called.
        """
        if self._delegate is None:
            return CommandResult(
                success=False,
                message="ToggleDateExceptionCommand: nothing to undo (execute not called).",
            )
        return self._delegate.undo()


# ---------------------------------------------------------------------------
# Regeneration command
# ---------------------------------------------------------------------------

class RegenerateSchedulesCommand(Command):
    """
    Recompute exam schedules and persist them to the application cache.

    Calls ``ExamScheduleGenerator.generate_exam_systems()`` with the
    current courses and exam periods, then writes the result to
    ``CacheManager.set_generated_schedules()``.

    ``undo()`` is not supported: regeneration is a read-only computation that
    does not lose information (the inputs remain unchanged), so reversing it
    is equivalent to running it again with the previous inputs.

    Parameters
    ----------
    schedule_generator:
        An ``ExamScheduleGenerator`` instance used to run the computation.
    cache_manager:
        The application ``CacheManager`` that will receive the new schedules.
    courses:
        The course list to schedule.
    exam_periods:
        The exam periods to schedule over.
    """

    def __init__(
        self,
        schedule_generator,
        cache_manager,
        courses: list,
        exam_periods: list,
    ) -> None:
        self._generator = schedule_generator
        self._cache = cache_manager
        self._courses = courses
        self._exam_periods = exam_periods

    def execute(self) -> CommandResult:
        """
        Run the schedule generator and persist the result.

        Returns
        -------
        CommandResult
            ``success=True`` with the new ``list[ExamSystem]`` in ``data``.
            On unexpected errors a ``success=False`` result is returned with
            the error description in ``message``.
        """
        try:
            schedules = self._generator.generate_exam_systems(
                self._courses, self._exam_periods
            )
            self._cache.set_generated_schedules(schedules)
            count = len(schedules)
            return CommandResult(
                success=True,
                message=f"Generated {count} exam system{'s' if count != 1 else ''}.",
                data=schedules,
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                success=False,
                message=f"Schedule regeneration failed: {exc}",
            )
# ---------------------------------------------------------------------------
# Semester-period editing command
# ---------------------------------------------------------------------------

class EditPeriodCommand(Command):
    """
    Edit the start and/or end date of an exam period.

    The Date Management screen (SCRUM-124) lets the user adjust the scheduling
    window of an ``ExamPeriod`` directly in the GUI.  This command wraps that
    mutation so it stays consistent with the rest of the calendar actions: it
    is created by the Presenter (the Invoker), it returns a ``CommandResult``
    carrying the refreshed valid-date list, and it supports one-step ``undo``.

    Validation
    ----------
    The command rejects an inverted range (start after end) by returning a
    ``success=False`` result, mirroring the guard already enforced by
    ``ExamDateHandler.generate_dates``.  This keeps the failure inside the
    command/result envelope instead of letting a ``ValueError`` escape into
    the View.

    Excluded dates
    --------------
    Excluded dates are intentionally left untouched when the window changes.
    ``ExamDateHandler`` already ignores any excluded date that falls outside
    the active range, so an exclusion that lands outside the new window is
    harmless and simply becomes inactive — no silent purging is performed.

    Undo
    ----
    ``undo()`` restores the exact ``start_date``/``end_date`` captured before
    ``execute()`` ran, allowing the Presenter to offer a one-step revert just
    like the date-toggle commands.

    Parameters
    ----------
    exam_period:
        The ``ExamPeriod`` whose scheduling window will be edited.
    date_handler:
        An ``ExamDateHandler`` instance used to recompute valid dates after
        the edit so the View can redraw the calendar.
    new_start_date:
        The requested new ``start_date`` for the period.
    new_end_date:
        The requested new ``end_date`` for the period.
    """

    def __init__(
        self,
        exam_period,
        date_handler,
        new_start_date: date,
        new_end_date: date,
    ) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._new_start_date = new_start_date
        self._new_end_date = new_end_date
        # Snapshots captured at execute-time so undo() can restore them.
        self._previous_start_date: date | None = None
        self._previous_end_date: date | None = None
        # Tracks whether execute() actually applied the change, so a failed or
        # un-run command never tries to undo a mutation that never happened.
        self._did_edit: bool = False

    def execute(self) -> CommandResult:
        """
        Apply the new start/end dates to the exam period.

        Returns
        -------
        CommandResult
            ``success=True`` with the updated ``list[date]`` of valid dates in
            ``data``.  Returns ``success=False`` (and leaves the period
            unchanged) if ``new_start_date`` is after ``new_end_date``.
        """
        # Reject an inverted window up front; the period is left untouched.
        if self._new_start_date > self._new_end_date:
            return CommandResult(
                success=False,
                message="Period start date cannot be after end date.",
            )

        # Capture the current window before overwriting it, so undo() can
        # restore the exact previous values.
        self._previous_start_date = self._exam_period.start_date
        self._previous_end_date = self._exam_period.end_date

        self._exam_period.start_date = self._new_start_date
        self._exam_period.end_date = self._new_end_date
        self._did_edit = True

        valid_dates = self._date_handler.get_valid_dates(self._exam_period)
        start_text = self._new_start_date.strftime("%d-%m-%Y")
        end_text = self._new_end_date.strftime("%d-%m-%Y")
        return CommandResult(
            success=True,
            message=f"Exam period updated to {start_text} - {end_text}.",
            data=valid_dates,
        )

    def undo(self) -> CommandResult:
        """
        Restore the start/end dates captured before ``execute()`` ran.

        Returns
        -------
        CommandResult
            ``success=True`` with the refreshed valid-date list in ``data``.
            Returns ``success=False`` if the command was never executed (or
            its execution failed), so there is nothing to revert.
        """
        if not self._did_edit:
            return CommandResult(
                success=False,
                message="EditPeriodCommand: nothing to undo (edit was not applied).",
            )

        self._exam_period.start_date = self._previous_start_date
        self._exam_period.end_date = self._previous_end_date
        self._did_edit = False

        valid_dates = self._date_handler.get_valid_dates(self._exam_period)
        return CommandResult(
            success=True,
            message="Exam period edit reversed.",
            data=valid_dates,
        )


# ---------------------------------------------------------------------------
# Manual schedule move commands
# ---------------------------------------------------------------------------

class ScheduleModificationCommand(Command):
    """Move one exam inside the active schedule and support undo/redo."""

    def __init__(
        self,
        schedule_getter: Callable[[], ExamSystem],
        schedule_setter: Callable[[ExamSystem], None],
        course_id: str,
        new_date: date | str,
        *,
        editor: ManualScheduleEditor | None = None,
        constraint_settings: SchedulingConstraintSettings | None = None,
        available_dates: set[date] | list[date] | tuple[date, ...] | None = None,
    ) -> None:
        self._schedule_getter = schedule_getter
        self._schedule_setter = schedule_setter
        self._course_id = course_id
        self._new_date = new_date
        self._editor = editor or ManualScheduleEditor()
        self._constraint_settings = constraint_settings
        self._available_dates = available_dates
        self._old_schedule: ExamSystem | None = None
        self._new_schedule: ExamSystem | None = None
        self._old_date: date | None = None
        self._applied = False

    @property
    def course_id(self) -> str:
        """Return the moved course id."""
        return self._course_id

    @property
    def old_date(self) -> date | None:
        """Return the date captured before execute."""
        return self._old_date

    @property
    def new_date(self) -> date | str:
        """Return the requested new date."""
        return self._new_date

    def execute(self) -> CommandResult:
        """Apply the move to the active schedule."""
        current_schedule = self._schedule_getter()
        result = self._editor.move_exam(
            current_schedule,
            self._course_id,
            self._new_date,
            constraint_settings=self._constraint_settings,
            available_dates=self._available_dates,
        )

        if not result.success or result.schedule is None:
            return CommandResult(
                success=False,
                message=result.message,
                data=result,
            )

        self._old_schedule = deepcopy(current_schedule)
        self._new_schedule = deepcopy(result.schedule)
        self._old_date = result.old_date
        self._schedule_setter(deepcopy(result.schedule))
        self._applied = True

        return CommandResult(
            success=True,
            message=result.message,
            data=result,
        )

    def undo(self) -> CommandResult:
        """Restore the schedule captured before execute."""
        if not self._applied or self._old_schedule is None:
            return CommandResult(
                success=False,
                message="ScheduleModificationCommand: nothing to undo.",
            )

        self._schedule_setter(deepcopy(self._old_schedule))
        self._applied = False
        return CommandResult(
            success=True,
            message=f"Manual move for course {self._course_id} was undone.",
            data=deepcopy(self._old_schedule),
        )

    def redo(self) -> CommandResult:
        """Apply the stored new schedule again without regenerating anything."""
        if self._new_schedule is None:
            return CommandResult(
                success=False,
                message="ScheduleModificationCommand: nothing to redo.",
            )

        self._schedule_setter(deepcopy(self._new_schedule))
        self._applied = True
        return CommandResult(
            success=True,
            message=f"Manual move for course {self._course_id} was redone.",
            data=deepcopy(self._new_schedule),
        )


class UndoRedoManager:
    """Stores the last successful manual move commands."""

    def __init__(self, history_limit: int = 20) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit must be greater than zero.")

        self._history_limit = history_limit
        self._undo_stack: list[ScheduleModificationCommand] = []
        self._redo_stack: list[ScheduleModificationCommand] = []

    @property
    def undo_count(self) -> int:
        """Return how many moves can be undone."""
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        """Return how many moves can be redone."""
        return len(self._redo_stack)

    def execute(self, command: ScheduleModificationCommand) -> CommandResult:
        """Run a command and store it only when it succeeds."""
        result = command.execute()
        if not result.success:
            return result

        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._trim_history()
        return result

    def undo(self) -> CommandResult:
        """Undo the latest successful manual move."""
        if not self._undo_stack:
            return CommandResult(success=False, message="No manual move to undo.")

        command = self._undo_stack.pop()
        result = command.undo()
        if result.success:
            self._redo_stack.append(command)
        else:
            self._undo_stack.append(command)
        return result

    def redo(self) -> CommandResult:
        """Redo the latest undone manual move."""
        if not self._redo_stack:
            return CommandResult(success=False, message="No manual move to redo.")

        command = self._redo_stack.pop()
        result = command.redo()
        if result.success:
            self._undo_stack.append(command)
            self._trim_history()
        else:
            self._redo_stack.append(command)
        return result

    def clear(self) -> None:
        """Forget all undo and redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _trim_history(self) -> None:
        while len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
