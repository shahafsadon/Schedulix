"""
test_date_management_screen.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Headless unit tests for the Date Management screen helper (SCRUM-124).

The screen itself is a passive customtkinter View and needs a display to build,
so it is verified manually (visual test) and via a headless smoke test. What we
*can* and *should* pin down with a portable unit test is the date-parsing rule
the View relies on, since a wrong format here would silently break the
"Edit semester periods" feature.

``parse_calendar_date`` is intentionally a module-level function (not a method)
precisely so it can be imported and tested without constructing any widget.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[2]   # tests/
_SRC = _TESTS_ROOT.parent / "src"                   # src/

sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

from gui.screens.dateManagementScreen import parse_calendar_date


class TestParseCalendarDate(unittest.TestCase):
    """Unit tests for the DD-MM-YYYY date parser used by the edit panel."""

    def test_parses_valid_ddmmyyyy(self) -> None:
        """A well-formed DD-MM-YYYY string parses to the matching date."""
        self.assertEqual(parse_calendar_date("29-01-2026"), date(2026, 1, 29))

    def test_strips_surrounding_whitespace(self) -> None:
        """Leading/trailing spaces are tolerated (entry fields often add them)."""
        self.assertEqual(parse_calendar_date("  05-02-2026  "), date(2026, 2, 5))

    def test_rejects_wrong_separator(self) -> None:
        """A slash-separated date is rejected (the input format uses dashes)."""
        with self.assertRaises(ValueError):
            parse_calendar_date("29/01/2026")

    def test_rejects_non_date_text(self) -> None:
        """Free text that is not a date raises ValueError for the View to catch."""
        with self.assertRaises(ValueError):
            parse_calendar_date("not a date")


if __name__ == "__main__":
    unittest.main()