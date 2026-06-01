"""Presenter for the study-program selection screen (SCRUM-122).

This module holds the logic for the program-selection step of the Version 2.0
GUI wizard. Following the MVP pattern, the presenter contains no customTkinter
code, so it can be unit tested without launching a GUI. The View calls these
methods in response to user actions and renders the returned data.
"""
from __future__ import annotations

from dataclasses import dataclass

from models import Course

# Maximum number of programs a user may select, per the Version 1.0 rules.
DEFAULT_MAX_PROGRAMS = 5


@dataclass(frozen=True)
class SelectionChange:
    """Result of a single toggle action.

    The View uses `accepted` to keep or revert the checkbox change, and
    `message` to show short feedback to the user.
    """

    accepted: bool
    message: str = ""


class ProgramSelectionPresenter:
    """Drives the program-selection screen.

    The presenter receives the loaded courses, derives the list of programs the
    user may choose from, tracks the current selection, and enforces the
    maximum-selection rule.
    """

    def __init__(
        self,
        courses: list[Course],
        max_programs: int = DEFAULT_MAX_PROGRAMS,
    ) -> None:
        # Selectable programs are exactly those that appear in the loaded
        # courses, matching the requirement that the on-screen list is built
        # from the courses file rather than a fixed catalog.
        self._available_programs = self._derive_available_programs(courses)
        # A set gives fast membership checks; callers always receive a sorted
        # list so the View and tests see stable ordering.
        self._selected_programs: set[str] = set()
        self.max_programs = max_programs

    @property
    def available_programs(self) -> list[str]:
        """Return the selectable program numbers, sorted for stable display."""
        return list(self._available_programs)

    @property
    def selected_programs(self) -> list[str]:
        """Return the currently selected program numbers, sorted."""
        return sorted(self._selected_programs)

    def is_selected(self, program_number: str) -> bool:
        """Return True if the given program is currently selected."""
        return program_number in self._selected_programs

    def selection_count(self) -> int:
        """Return how many programs are currently selected."""
        return len(self._selected_programs)

    def remaining_slots(self) -> int:
        """Return how many more programs can still be selected."""
        return self.max_programs - self.selection_count()

    def can_proceed(self) -> bool:
        """Return True when the selection is valid to move to the next step.

        At least one program must be selected before scheduling makes sense.
        """
        return 1 <= self.selection_count() <= self.max_programs

    def toggle(self, program_number: str) -> SelectionChange:
        """Select the program if not selected, otherwise deselect it.

        Selecting is rejected when the program is unknown or when the maximum
        number of programs is already selected. Deselecting always succeeds.
        """
        if program_number not in self._available_programs:
            return SelectionChange(
                accepted=False,
                message=f"Unknown program: {program_number}",
            )

        if program_number in self._selected_programs:
            self._selected_programs.discard(program_number)
            return SelectionChange(accepted=True)

        if self.selection_count() >= self.max_programs:
            return SelectionChange(
                accepted=False,
                message=f"You can select at most {self.max_programs} programs.",
            )

        self._selected_programs.add(program_number)
        return SelectionChange(accepted=True)

    def clear(self) -> None:
        """Remove all selected programs."""
        self._selected_programs.clear()

    @staticmethod
    def _derive_available_programs(courses: list[Course]) -> list[str]:
        """Collect the unique program numbers found across all courses.

        Every course carries one ProgramEnrollment per program it belongs to;
        the union of those program numbers is the set the user may choose from.
        """
        programs: set[str] = set()
        for course in courses:
            for enrollment in course.programs:
                programs.add(enrollment.program_number)
        return sorted(programs)