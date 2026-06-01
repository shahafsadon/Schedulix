"""Integration tests for the program configuration flow (SCRUM-122 + SCRUM-123).

These tests exercise the two presenters together, the way the unified
ProgramConfigScreen uses them, against the real example data. They prove the
hand-off works: every program a user can select and inspect produces coherent
selection behavior and coherent details.

The View itself (customTkinter) is intentionally not instantiated here: per the
MVP design, all logic lives in the presenters, so the integration is verified at
the presenter level without needing a display.
"""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from gui.programSelectionPresenter import ProgramSelectionPresenter
from gui.programDetailsPresenter import ProgramDetailsPresenter


EXAMPLE_COURSES = ROOT / "data" / "examples" / "CourseExample.txt"


class ProgramConfigFlowTests(unittest.TestCase):
    """Selection and details presenters working together on real data."""

    def setUp(self) -> None:
        courses = CoursesFileReader().read(EXAMPLE_COURSES)
        self.selection = ProgramSelectionPresenter(courses)
        self.details = ProgramDetailsPresenter(courses)

    def test_example_file_exposes_programs(self) -> None:
        """The example courses file must yield at least one selectable program."""
        self.assertTrue(self.selection.available_programs)

    def test_every_selectable_program_has_coherent_details(self) -> None:
        """Each program offered for selection can also be inspected."""
        for program in self.selection.available_programs:
            details = self.details.get_details(program)
            self.assertEqual(details.program_number, program)
            self.assertGreater(details.course_count, 0)
            self.assertTrue(details.groups)

    def test_inspecting_does_not_change_selection(self) -> None:
        """Expanding a row (details) must not select the program."""
        program = self.selection.available_programs[0]
        # Fetching details is a read-only inspection action.
        self.details.get_details(program)
        self.assertFalse(self.selection.is_selected(program))
        self.assertEqual(self.selection.selection_count(), 0)

    def test_selecting_all_example_programs_allows_proceeding(self) -> None:
        """Selecting the example programs (3 < 5) enables moving on."""
        for program in self.selection.available_programs:
            self.assertTrue(self.selection.toggle(program).accepted)
        self.assertTrue(self.selection.can_proceed())

    def test_program_outside_list_has_empty_details(self) -> None:
        """A program number not in the data yields an empty details view."""
        empty = self.details.get_details("00000")
        self.assertEqual(empty.course_count, 0)
        self.assertEqual(empty.groups, [])


if __name__ == "__main__":
    unittest.main()