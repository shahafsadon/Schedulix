"""
test_edit_period_command.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Isolated unit tests for the semester-period editing feature (SCRUM-124).

Tests cover:
* EditPeriodCommand
    - execute() applies the new window and returns refreshed valid dates
    - execute() rejects an inverted range without mutating the period
    - undo() restores the previous window
    - undo() guards against a command that was never executed
* DateManagementPresenter.on_edit_period
    - wires the command correctly and returns its result
    - a successful edit is stored so undo_last can reverse it
    - a rejected (inverted) edit is NOT stored for undo

No customtkinter or GUI dependencies — fully headless, runnable under both
``unittest`` and ``pytest``.
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
# Imports under test
# ---------------------------------------------------------------------------

from models import ExamPeriod
from scheduling.examDateHandler import ExamDateHandler
from application.commands import EditPeriodCommand
from gui.dateManagementPresenter import DateManagementPresenter


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_period(
    excluded: list[date] | None = None,
) -> ExamPeriod:
    """Return a five-day exam period (Jan 1–5, 2026) for editing tests."""
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        excluded_dates=list(excluded or []),
    )


_HANDLER = ExamDateHandler()

# Dates reused across tests.
JAN1 = date(2026, 1, 1)
JAN3 = date(2026, 1, 3)
JAN10 = date(2026, 1, 10)
JAN20 = date(2026, 1, 20)


# ---------------------------------------------------------------------------
# EditPeriodCommand
# ---------------------------------------------------------------------------

class TestEditPeriodCommand(unittest.TestCase):
    """Unit tests for the EditPeriodCommand in isolation."""

    def setUp(self) -> None:
        """Create a fresh five-day period and a stateless date handler."""
        self.period = _make_period()
        self.handler = _HANDLER

    def test_execute_applies_new_window_and_returns_valid_dates(self) -> None:
        """execute() should overwrite start/end and return the new valid dates."""
        command = EditPeriodCommand(self.period, self.handler, JAN10, JAN20)
        result = command.execute()

        self.assertTrue(result.success)
        # The period now spans Jan 10–20, 2026.
        self.assertEqual(self.period.start_date, JAN10)
        self.assertEqual(self.period.end_date, JAN20)
        # data carries the refreshed valid-date list: 11 days inclusive.
        self.assertEqual(len(result.data), 11)
        self.assertEqual(result.data[0], JAN10)
        self.assertEqual(result.data[-1], JAN20)

    def test_execute_rejects_inverted_range_without_mutating(self) -> None:
        """An inverted range (start after end) is rejected; period unchanged."""
        command = EditPeriodCommand(self.period, self.handler, JAN20, JAN10)
        result = command.execute()

        self.assertFalse(result.success)
        # The original Jan 1–5 window must be intact.
        self.assertEqual(self.period.start_date, JAN1)
        self.assertEqual(self.period.end_date, date(2026, 1, 5))

    def test_undo_restores_previous_window(self) -> None:
        """undo() should restore the exact start/end captured before execute()."""
        command = EditPeriodCommand(self.period, self.handler, JAN10, JAN20)
        command.execute()

        undo_result = command.undo()

        self.assertTrue(undo_result.success)
        # Back to the original Jan 1–5 window.
        self.assertEqual(self.period.start_date, JAN1)
        self.assertEqual(self.period.end_date, date(2026, 1, 5))
        # Valid-date list reflects the restored 5-day window.
        self.assertEqual(len(undo_result.data), 5)

    def test_undo_guards_when_not_executed(self) -> None:
        """undo() on a command that never ran (or was rejected) must fail safely."""
        command = EditPeriodCommand(self.period, self.handler, JAN10, JAN20)
        # No execute() call — there is nothing to revert.
        result = command.undo()

        self.assertFalse(result.success)
        # Period stays at its original window.
        self.assertEqual(self.period.start_date, JAN1)


# ---------------------------------------------------------------------------
# DateManagementPresenter.on_edit_period
# ---------------------------------------------------------------------------

class TestPresenterOnEditPeriod(unittest.TestCase):
    """Unit tests for the presenter's on_edit_period wiring and undo support."""

    def setUp(self) -> None:
        """Build a presenter over a fresh period; cache/generator unused here."""
        self.period = _make_period()
        # CacheManager and generator are not exercised by edit/undo, so plain
        # placeholders are sufficient and keep the test fully headless.
        self.presenter = DateManagementPresenter(
            exam_period=self.period,
            date_handler=_HANDLER,
            cache_manager=None,
        )

    def test_on_edit_period_applies_window(self) -> None:
        """on_edit_period should mutate the period and return a success result."""
        result = self.presenter.on_edit_period(JAN10, JAN20)

        self.assertTrue(result.success)
        self.assertEqual(self.period.start_date, JAN10)
        self.assertEqual(self.period.end_date, JAN20)

    def test_successful_edit_is_undoable_via_undo_last(self) -> None:
        """A successful edit is stored, so undo_last reverses it."""
        self.presenter.on_edit_period(JAN10, JAN20)

        undo_result = self.presenter.undo_last()

        self.assertTrue(undo_result.success)
        # The original window is restored.
        self.assertEqual(self.period.start_date, JAN1)
        self.assertEqual(self.period.end_date, date(2026, 1, 5))

    def test_rejected_edit_is_not_stored_for_undo(self) -> None:
        """An inverted-range edit fails and leaves nothing to undo."""
        edit_result = self.presenter.on_edit_period(JAN20, JAN10)
        self.assertFalse(edit_result.success)

        # Because the edit was rejected, undo_last has nothing to reverse.
        undo_result = self.presenter.undo_last()
        self.assertFalse(undo_result.success)


if __name__ == "__main__":
    unittest.main()