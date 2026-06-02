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

* The **receiver** that commands mutate is ``ExamPeriod``.  ``ExamDateHandler``
  is stateless and is used as a *tool* to recompute the valid-date list.
* Commands are instantiated by the Presenter (the Invoker) with all their
  dependencies injected via constructor arguments — no Singleton references.
* ``undo()`` is supported on every command that mutates state.

No Version 1.0 source files are modified by this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


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
    one-step revert; the default implementation returns a failure result.
    """

    @abstractmethod
    def execute(self) -> CommandResult:
        """Perform the action this command represents."""
        ...

    def undo(self) -> CommandResult:
        """
        Reverse the effect of the most recent ``execute()`` call.

        The default implementation returns a failure result.  Subclasses that
        mutate state should override this method.
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

    Supports ``undo()``: removes the date from ``excluded_dates`` again.
    """

    def __init__(self, exam_period, date_handler, target_date: date) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._target_date = target_date
        self._did_add: bool = False

    def execute(self) -> CommandResult:
        """Append ``target_date`` to ``exam_period.excluded_dates`` if absent."""
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
        """Remove ``target_date`` from ``exam_period.excluded_dates``."""
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

    Supports ``undo()``: adds the date back to ``excluded_dates``.
    """

    def __init__(self, exam_period, date_handler, target_date: date) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._target_date = target_date
        self._did_remove: bool = False

    def execute(self) -> CommandResult:
        """Remove ``target_date`` from ``exam_period.excluded_dates`` if present."""
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
        """Re-exclude ``target_date`` in ``exam_period.excluded_dates``."""
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

    Delegates to ``ExcludeDateCommand`` or ``ActivateDateCommand`` depending
    on the current state.  ``undo()`` reverses the toggle.
    """

    def __init__(self, exam_period, date_handler, target_date: date) -> None:
        self._exam_period = exam_period
        self._date_handler = date_handler
        self._target_date = target_date
        self._delegate: Command | None = None

    def execute(self) -> CommandResult:
        """Exclude if active; activate if excluded."""
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
        """Reverse the most recent toggle."""
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

    ``undo()`` is not supported — regeneration is a pure computation.
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
        """Run the schedule generator and persist the result."""
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
