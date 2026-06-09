"""Unit tests for ProgramSelectionPresenter (SCRUM-122).

These tests verify the program-selection logic in isolation: which programs are
offered, how toggling selects and deselects them, the five-program maximum, and
when the user is allowed to proceed. No GUI is involved, which is the benefit of
the MVP split: the rules are tested without launching customTkinter.
"""
import sys
import unittest
from pathlib import Path


# Tests live three levels below the repo root; add src/ to the path so the
# production modules import the same way they do when the app runs.
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from models import Course, ProgramEnrollment
from gui.presenters.programSelectionPresenter import ProgramSelectionPresenter


def make_course(course_number: str, program_numbers: list[str]) -> Course:
    """Build a small Course attached to one or more programs.

    Only the program enrollments matter for selection tests, so the other course
    fields are filled with fixed placeholder values to keep each test concise.
    """
    return Course(
        name=f"Course {course_number}",
        course_number=course_number,
        instructor="Test Instructor",
        programs=[
            ProgramEnrollment(program_number, 1, "FALL", "Obligatory")
            for program_number in program_numbers
        ],
        evaluation_type="Exam",
    )


class ProgramSelectionPresenterTests(unittest.TestCase):
    """Tests for the program-selection logic (no GUI involved)."""

    def test_available_programs_are_unique_and_sorted(self) -> None:
        """Selectable programs are the de-duplicated, sorted union across courses."""
        # "83101" appears on both courses but should be offered only once.
        courses = [
            make_course("83102", ["83101", "83108"]),
            make_course("83112", ["83101"]),
        ]
        presenter = ProgramSelectionPresenter(courses)
        self.assertEqual(presenter.available_programs, ["83101", "83108"])

    def test_toggle_selects_then_deselects(self) -> None:
        """Toggling the same program twice selects it, then deselects it."""
        presenter = ProgramSelectionPresenter([make_course("83102", ["83101"])])
        # First toggle: not selected -> selected.
        first = presenter.toggle("83101")
        self.assertTrue(first.accepted)
        self.assertTrue(presenter.is_selected("83101"))
        # Second toggle on the same program: selected -> deselected.
        second = presenter.toggle("83101")
        self.assertTrue(second.accepted)
        self.assertFalse(presenter.is_selected("83101"))

    def test_cannot_select_more_than_max(self) -> None:
        """Selecting beyond the maximum is rejected and the count stays capped."""
        # Six selectable programs, limit of five, so the sixth must be refused.
        courses = [make_course("100", [f"8310{i}" for i in range(6)])]
        presenter = ProgramSelectionPresenter(courses, max_programs=5)
        available = presenter.available_programs
        # Selecting the first five is allowed.
        for program in available[:5]:
            self.assertTrue(presenter.toggle(program).accepted)
        # The sixth is rejected and the selection remains at the cap of five.
        rejected = presenter.toggle(available[5])
        self.assertFalse(rejected.accepted)
        self.assertEqual(presenter.selection_count(), 5)

    def test_toggle_rejects_unknown_program(self) -> None:
        """A program not in the available list cannot be selected."""
        presenter = ProgramSelectionPresenter([make_course("83102", ["83101"])])
        result = presenter.toggle("99999")
        self.assertFalse(result.accepted)
        self.assertFalse(presenter.is_selected("99999"))

    def test_can_proceed_requires_between_one_and_max(self) -> None:
        """The user may proceed only after selecting at least one program."""
        presenter = ProgramSelectionPresenter([make_course("83102", ["83101"])])
        # Nothing selected yet -> cannot proceed.
        self.assertFalse(presenter.can_proceed())
        # One program selected -> can proceed.
        presenter.toggle("83101")
        self.assertTrue(presenter.can_proceed())

    def test_initial_selection_is_restored_from_cache(self) -> None:
        """Known cached selections start checked; unknown ones are ignored."""
        presenter = ProgramSelectionPresenter(
            [make_course("83102", ["83101"])],
            selected_programs=["83101", "99999"],
        )

        self.assertEqual(presenter.selected_programs, ["83101"])
        self.assertTrue(presenter.is_selected("83101"))
        self.assertFalse(presenter.is_selected("99999"))

    def test_selected_programs_returns_sorted_list(self) -> None:
        """The selected programs are returned sorted, regardless of click order."""
        courses = [make_course("100", ["83108", "83101", "83104"])]
        presenter = ProgramSelectionPresenter(courses)
        # Selected out of order to prove the output is sorted, not insertion-order.
        presenter.toggle("83108")
        presenter.toggle("83101")
        self.assertEqual(presenter.selected_programs, ["83101", "83108"])


if __name__ == "__main__":
    unittest.main()
