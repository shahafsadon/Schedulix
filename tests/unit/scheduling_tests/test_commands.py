"""
test_commands.py
~~~~~~~~~~~~~~~~
Isolated unit tests for the Command infrastructure (SCRUM-114).

Tests cover:
* ExcludeDateCommand   — blocks a date, idempotent, undo
* ActivateDateCommand  — unblocks a date, no-op safe, undo
* ToggleDateExceptionCommand — full toggle cycle, undo, no-execute guard
* RegenerateSchedulesCommand — writes to cache, empty inputs, error path
* DateManagementPresenter — wires commands correctly, undo_last, regenerate

No customtkinter or GUI dependencies — fully headless.
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

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
from application.commands import (
    ActivateDateCommand,
    Command,
    CommandResult,
    ExcludeDateCommand,
    RegenerateSchedulesCommand,
    ToggleDateExceptionCommand,
)
from gui.presenters.dateManagementPresenter import DateManagementPresenter


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_period(
    excluded: list[date] | None = None,
) -> ExamPeriod:
    """Return a simple three-day exam period for January 2026."""
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        excluded_dates=list(excluded or []),
    )


_HANDLER = ExamDateHandler()

# Dates used across tests
JAN1 = date(2026, 1, 1)
JAN2 = date(2026, 1, 2)
JAN3 = date(2026, 1, 3)


# ---------------------------------------------------------------------------
# Command ABC
# ---------------------------------------------------------------------------

class TestCommandABC(unittest.TestCase):
    """Verify the abstract contract cannot be instantiated directly."""

    def test_command_is_abstract(self) -> None:
        """Command cannot be instantiated without implementing execute()."""
        with self.assertRaises(TypeError):
            Command()  # type: ignore[abstract]

    def test_default_undo_returns_failure(self) -> None:
        """A concrete subclass that does not override undo() gets a failure result."""

        class _Minimal(Command):
            def execute(self) -> CommandResult:
                return CommandResult(success=True)

        result = _Minimal().undo()
        self.assertFalse(result.success)
        self.assertIn("does not support undo", result.message)


# ---------------------------------------------------------------------------
# ExcludeDateCommand
# ---------------------------------------------------------------------------

class TestExcludeDateCommand(unittest.TestCase):
    """ExcludeDateCommand adds a date to excluded_dates and recomputes valid dates."""

    def test_execute_adds_date_to_excluded(self) -> None:
        """After execute(), target_date appears in exam_period.excluded_dates."""
        period = _make_period()
        cmd = ExcludeDateCommand(period, _HANDLER, JAN3)

        cmd.execute()

        self.assertIn(JAN3, period.excluded_dates)

    def test_execute_returns_updated_valid_dates(self) -> None:
        """The result data is the valid-date list with target_date removed."""
        period = _make_period()
        cmd = ExcludeDateCommand(period, _HANDLER, JAN3)

        result = cmd.execute()

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, result.data)
        self.assertIn(JAN1, result.data)

    def test_execute_is_idempotent(self) -> None:
        """Calling execute() twice does not add a duplicate to excluded_dates."""
        period = _make_period()
        cmd = ExcludeDateCommand(period, _HANDLER, JAN3)

        cmd.execute()
        cmd.execute()

        self.assertEqual(period.excluded_dates.count(JAN3), 1)

    def test_undo_removes_date_from_excluded(self) -> None:
        """undo() removes the date that execute() added."""
        period = _make_period()
        cmd = ExcludeDateCommand(period, _HANDLER, JAN3)
        cmd.execute()

        result = cmd.undo()

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)
        self.assertIn(JAN3, result.data)

    def test_undo_before_execute_is_safe(self) -> None:
        """Calling undo() before execute() does not crash or corrupt state."""
        period = _make_period()
        cmd = ExcludeDateCommand(period, _HANDLER, JAN3)

        result = cmd.undo()

        # The date was never added, so the period should still be clean.
        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)


# ---------------------------------------------------------------------------
# ActivateDateCommand
# ---------------------------------------------------------------------------

class TestActivateDateCommand(unittest.TestCase):
    """ActivateDateCommand removes a date from excluded_dates."""

    def test_execute_removes_date_from_excluded(self) -> None:
        """After execute(), target_date is no longer in excluded_dates."""
        period = _make_period(excluded=[JAN3])
        cmd = ActivateDateCommand(period, _HANDLER, JAN3)

        cmd.execute()

        self.assertNotIn(JAN3, period.excluded_dates)

    def test_execute_returns_updated_valid_dates(self) -> None:
        """The result data includes target_date after it is unblocked."""
        period = _make_period(excluded=[JAN3])
        cmd = ActivateDateCommand(period, _HANDLER, JAN3)

        result = cmd.execute()

        self.assertTrue(result.success)
        self.assertIn(JAN3, result.data)

    def test_execute_is_noop_when_not_excluded(self) -> None:
        """execute() on an already-active date succeeds without side-effects."""
        period = _make_period()
        before = list(period.excluded_dates)
        cmd = ActivateDateCommand(period, _HANDLER, JAN3)

        result = cmd.execute()

        self.assertTrue(result.success)
        self.assertEqual(period.excluded_dates, before)

    def test_undo_re_adds_date_to_excluded(self) -> None:
        """undo() puts the date back into excluded_dates after an activate."""
        period = _make_period(excluded=[JAN3])
        cmd = ActivateDateCommand(period, _HANDLER, JAN3)
        cmd.execute()

        result = cmd.undo()

        self.assertTrue(result.success)
        self.assertIn(JAN3, period.excluded_dates)
        self.assertNotIn(JAN3, result.data)

    def test_undo_before_execute_is_safe(self) -> None:
        """Calling undo() before execute() does not modify state."""
        period = _make_period()
        cmd = ActivateDateCommand(period, _HANDLER, JAN3)

        result = cmd.undo()

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)


# ---------------------------------------------------------------------------
# ToggleDateExceptionCommand
# ---------------------------------------------------------------------------

class TestToggleDateExceptionCommand(unittest.TestCase):
    """ToggleDateExceptionCommand delegates to Exclude or Activate based on state."""

    def test_execute_excludes_active_date(self) -> None:
        """Clicking an active date blocks it."""
        period = _make_period()
        cmd = ToggleDateExceptionCommand(period, _HANDLER, JAN3)

        result = cmd.execute()

        self.assertTrue(result.success)
        self.assertIn(JAN3, period.excluded_dates)

    def test_execute_activates_excluded_date(self) -> None:
        """Clicking a blocked date unblocks it."""
        period = _make_period(excluded=[JAN3])
        cmd = ToggleDateExceptionCommand(period, _HANDLER, JAN3)

        result = cmd.execute()

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)

    def test_double_toggle_restores_original_state(self) -> None:
        """Two sequential toggles leave the period in its original state."""
        period = _make_period()
        original_excluded = list(period.excluded_dates)

        cmd1 = ToggleDateExceptionCommand(period, _HANDLER, JAN3)
        cmd1.execute()
        cmd2 = ToggleDateExceptionCommand(period, _HANDLER, JAN3)
        cmd2.execute()

        self.assertEqual(period.excluded_dates, original_excluded)

    def test_undo_reverses_exclusion(self) -> None:
        """undo() after an exclude-toggle restores the date as active."""
        period = _make_period()
        cmd = ToggleDateExceptionCommand(period, _HANDLER, JAN3)
        cmd.execute()  # now excluded

        result = cmd.undo()

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)

    def test_undo_before_execute_returns_failure(self) -> None:
        """undo() before execute() returns success=False with a clear message."""
        period = _make_period()
        cmd = ToggleDateExceptionCommand(period, _HANDLER, JAN3)

        result = cmd.undo()

        self.assertFalse(result.success)
        self.assertIn("execute not called", result.message)


# ---------------------------------------------------------------------------
# RegenerateSchedulesCommand
# ---------------------------------------------------------------------------

class TestRegenerateSchedulesCommand(unittest.TestCase):
    """RegenerateSchedulesCommand calls the generator and persists to cache."""

    def _make_mock_generator(self, schedules=None):
        mock = MagicMock()
        mock.generate_exam_systems.return_value = schedules or []
        return mock

    def _make_mock_cache(self):
        return MagicMock()

    def test_execute_writes_schedules_to_cache(self) -> None:
        """execute() calls cache.set_generated_schedules with generator output."""
        mock_schedules = [MagicMock(), MagicMock()]
        generator = self._make_mock_generator(mock_schedules)
        cache = self._make_mock_cache()
        cmd = RegenerateSchedulesCommand(generator, cache, [], [])

        cmd.execute()

        cache.set_generated_schedules.assert_called_once_with(mock_schedules)

    def test_execute_returns_success_true(self) -> None:
        """execute() returns success=True on a normal generator run."""
        generator = self._make_mock_generator([MagicMock()])
        cache = self._make_mock_cache()
        cmd = RegenerateSchedulesCommand(generator, cache, [], [])

        result = cmd.execute()

        self.assertTrue(result.success)

    def test_execute_data_matches_generator_output(self) -> None:
        """result.data is exactly the list returned by the generator."""
        schedules = [MagicMock(), MagicMock(), MagicMock()]
        generator = self._make_mock_generator(schedules)
        cache = self._make_mock_cache()
        cmd = RegenerateSchedulesCommand(generator, cache, [], [])

        result = cmd.execute()

        self.assertIs(result.data, schedules)

    def test_execute_handles_generator_exception(self) -> None:
        """execute() returns success=False if the generator raises."""
        generator = MagicMock()
        generator.generate_exam_systems.side_effect = RuntimeError("boom")
        cache = self._make_mock_cache()
        cmd = RegenerateSchedulesCommand(generator, cache, [], [])

        result = cmd.execute()

        self.assertFalse(result.success)
        self.assertIn("boom", result.message)

    def test_undo_returns_failure(self) -> None:
        """RegenerateSchedulesCommand does not support undo."""
        generator = self._make_mock_generator()
        cache = self._make_mock_cache()
        cmd = RegenerateSchedulesCommand(generator, cache, [], [])

        result = cmd.undo()

        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# DateManagementPresenter
# ---------------------------------------------------------------------------

class TestDateManagementPresenter(unittest.TestCase):
    """DateManagementPresenter correctly wires commands to View events."""

    def _make_presenter(self, excluded=None, generator=None, courses=None, periods=None):
        period = _make_period(excluded=excluded)
        cache = MagicMock()
        return (
            DateManagementPresenter(
                exam_period=period,
                date_handler=_HANDLER,
                cache_manager=cache,
                schedule_generator=generator,
                courses=courses or [],
                exam_periods=periods or [],
            ),
            period,
            cache,
        )

    def test_on_date_clicked_excludes_active_date(self) -> None:
        """Clicking an active date blocks it via the presenter."""
        presenter, period, _ = self._make_presenter()

        result = presenter.on_date_clicked(JAN3)

        self.assertTrue(result.success)
        self.assertIn(JAN3, period.excluded_dates)

    def test_on_date_clicked_activates_excluded_date(self) -> None:
        """Clicking a blocked date unblocks it via the presenter."""
        presenter, period, _ = self._make_presenter(excluded=[JAN3])

        result = presenter.on_date_clicked(JAN3)

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)

    def test_undo_last_reverses_click(self) -> None:
        """undo_last() reverses the most recent on_date_clicked call."""
        presenter, period, _ = self._make_presenter()
        presenter.on_date_clicked(JAN3)  # exclude JAN3

        result = presenter.undo_last()

        self.assertTrue(result.success)
        self.assertNotIn(JAN3, period.excluded_dates)

    def test_undo_last_without_prior_click_returns_failure(self) -> None:
        """undo_last() returns failure when nothing has been clicked yet."""
        presenter, _, _ = self._make_presenter()

        result = presenter.undo_last()

        self.assertFalse(result.success)
        self.assertIn("Nothing to undo", result.message)

    def test_on_regenerate_without_generator_returns_failure(self) -> None:
        """on_regenerate() returns failure when no generator was injected."""
        presenter, _, _ = self._make_presenter(generator=None)

        result = presenter.on_regenerate()

        self.assertFalse(result.success)
        self.assertIn("No schedule generator", result.message)

    def test_on_regenerate_calls_cache(self) -> None:
        """on_regenerate() writes the new schedules to the injected cache."""
        mock_generator = MagicMock()
        mock_generator.generate_exam_systems.return_value = [MagicMock()]
        presenter, _, cache = self._make_presenter(generator=mock_generator)

        presenter.on_regenerate()

        cache.set_generated_schedules.assert_called_once()

    def test_get_valid_dates_reflects_current_state(self) -> None:
        """get_valid_dates() returns dates consistent with excluded_dates."""
        presenter, period, _ = self._make_presenter(excluded=[JAN3])

        valid = presenter.get_valid_dates()

        self.assertNotIn(JAN3, valid)
        self.assertIn(JAN1, valid)

    def test_is_excluded_returns_correct_state(self) -> None:
        """is_excluded() mirrors the period's excluded_dates list."""
        presenter, _, _ = self._make_presenter(excluded=[JAN3])

        self.assertTrue(presenter.is_excluded(JAN3))
        self.assertFalse(presenter.is_excluded(JAN1))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
