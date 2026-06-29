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

import queue
import sys
import unittest
from types import SimpleNamespace
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

from gui.screens.dateManagementScreen import DateManagementScreen, parse_calendar_date
from gui.presenters.schedulingPresenter import GenerationResult
from models import ExamPeriod


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


class _FakePeriodPresenter:
    def __init__(self, period: ExamPeriod, hidden_count: int = 0) -> None:
        self._period = period
        self._hidden_count = hidden_count

    def current_period(self) -> ExamPeriod:
        return self._period

    def count_excluded_outside_window(self) -> int:
        return self._hidden_count

    def can_undo(self) -> bool:
        return False


class _FakeWidget:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)


class _FakeRunner:
    def __init__(self, result: GenerationResult | None = None, accepted: bool = True) -> None:
        self.result = result
        self.accepted = accepted

    def run(
        self,
        task,
        on_started=None,
        on_complete=None,
        on_error=None,
    ) -> bool:
        if not self.accepted:
            return False
        if on_started is not None:
            on_started()
        result = self.result if self.result is not None else task()
        if on_complete is not None:
            on_complete(result)
        return True

    def run_with_progress(
        self,
        task,
        on_started=None,
        on_complete=None,
        on_error=None,
    ) -> bool:
        if not self.accepted:
            return False
        if on_started is not None:
            on_started()
        result = (
            self.result
            if self.result is not None
            else task(SimpleNamespace(is_cancelled=False), lambda _update: None)
        )
        if on_complete is not None:
            on_complete(result)
        return True


class TestDateManagementScreenHelpers(unittest.TestCase):
    """Headless checks for screen helpers that protect production UX edges."""

    def test_period_option_labels_are_unique_even_for_duplicate_periods(self) -> None:
        period = ExamPeriod(
            semester="FALL",
            moed="Aleph",
            start_date=date(2026, 1, 29),
            end_date=date(2026, 3, 11),
            excluded_dates=[],
        )
        screen = DateManagementScreen.__new__(DateManagementScreen)
        screen._presenters = [
            _FakePeriodPresenter(period),
            _FakePeriodPresenter(period),
        ]

        labels = DateManagementScreen._period_option_labels(screen)

        self.assertEqual(len(set(labels)), 2)
        self.assertTrue(labels[0].startswith("1. FALL Aleph"))
        self.assertTrue(labels[1].startswith("2. FALL Aleph"))

    def test_hidden_exclusion_message_is_disclosed_when_present(self) -> None:
        screen = DateManagementScreen.__new__(DateManagementScreen)
        screen.presenter = _FakePeriodPresenter(
            ExamPeriod(
                semester="FALL",
                moed="Aleph",
                start_date=date(2026, 1, 29),
                end_date=date(2026, 3, 11),
                excluded_dates=[],
            ),
            hidden_count=2,
        )

        message = DateManagementScreen._message_with_hidden_exclusions(
            screen,
            "Click a calendar day.",
        )

        self.assertEqual(
            message,
            "Click a calendar day. 2 excluded dates are outside this window.",
        )

    def _generation_screen(self, result: GenerationResult, visited: list[str]):
        screen = DateManagementScreen.__new__(DateManagementScreen)
        period = ExamPeriod(
            semester="FALL",
            moed="Aleph",
            start_date=date(2026, 1, 29),
            end_date=date(2026, 3, 11),
            excluded_dates=[],
        )
        screen.presenter = _FakePeriodPresenter(period)
        screen._scheduling_presenter = type(
            "FakeSchedulingPresenter",
            (),
            {"generate": lambda self: result},
        )()
        screen._runner = _FakeRunner(result)
        screen._on_generation_success = lambda: visited.append("results")
        screen._generation_in_progress = False
        screen._status_label = _FakeWidget()
        screen._period_selector = _FakeWidget()
        screen._start_entry = _FakeWidget()
        screen._end_entry = _FakeWidget()
        screen._apply_button = _FakeWidget()
        screen._undo_button = _FakeWidget()
        screen._back_button = _FakeWidget()
        screen._generate_button = _FakeWidget()
        screen._day_cells = {"2026-01-29": _FakeWidget()}
        screen._progress_queue = queue.Queue(maxsize=1)
        screen._after_calls = []

        def after(delay, callback):
            screen._after_calls.append(delay)
            if delay != 50:
                callback()

        screen.after = after
        return screen

    def test_generation_success_locks_controls_and_navigates_to_results(self) -> None:
        visited: list[str] = []
        screen = self._generation_screen(
            GenerationResult(True, "Generated.", 297472),
            visited,
        )

        DateManagementScreen._handle_generate(screen)

        self.assertEqual(visited, ["results"])
        self.assertEqual(
            screen._status_label.options["text"],
            "297,472 schedule systems generated successfully.",
        )
        self.assertEqual(screen._generate_button.options["state"], "disabled")
        self.assertEqual(screen._generate_button.options["text"], "Generating...")
        self.assertEqual(screen._day_cells["2026-01-29"].options["state"], "disabled")
        self.assertIn(0, screen._after_calls)
        self.assertNotIn(900, screen._after_calls)

    def test_generation_failure_restores_controls_and_stays_on_screen(self) -> None:
        visited: list[str] = []
        screen = self._generation_screen(
            GenerationResult(False, "No exam periods loaded.", 0),
            visited,
        )

        DateManagementScreen._handle_generate(screen)

        self.assertEqual(visited, [])
        self.assertEqual(screen._status_label.options["text"], "")
        self.assertEqual(screen._generate_button.options["state"], "normal")
        self.assertEqual(screen._generate_button.options["text"], "Generate Exam Schedules")
        self.assertEqual(screen._day_cells["2026-01-29"].options["state"], "normal")

    def test_fallback_generation_asks_before_opening_compromise_schedules(self) -> None:
        visited: list[str] = []
        result = GenerationResult(
            True,
            "Fallback schedule: showing the best available compromise.",
            1,
            is_fallback=True,
        )
        screen = self._generation_screen(result, visited)
        confirmations: list[GenerationResult] = []
        screen._show_compromise_confirmation = confirmations.append

        DateManagementScreen._handle_generate(screen)

        self.assertEqual(visited, [])
        self.assertEqual(confirmations, [result])
        self.assertEqual(
            screen._status_label.options["text"],
            "Fallback schedule: showing the best available compromise.",
        )
        self.assertEqual(screen._generate_button.options["state"], "normal")
        self.assertEqual(screen._generate_button.options["text"], "Generate Exam Schedules")
        self.assertEqual(screen._day_cells["2026-01-29"].options["state"], "normal")

    def test_duplicate_generation_request_shows_busy_feedback(self) -> None:
        visited: list[str] = []
        screen = self._generation_screen(
            GenerationResult(True, "Generated.", 1),
            visited,
        )
        screen._runner = _FakeRunner(accepted=False)

        DateManagementScreen._handle_generate(screen)

        self.assertEqual(visited, [])
        self.assertEqual(screen._status_label.options["text"], "")

    def test_generation_uses_background_full_generation_path(self) -> None:
        """The base GUI Generate action must not apply the Top-N preview."""
        visited: list[str] = []
        result = GenerationResult(True, "Generated.", 1, displayed_count=1)
        screen = self._generation_screen(result, visited)
        screen._runner = _FakeRunner(result=None)
        calls: list[str] = []

        class FullGenerationPresenter:
            def generate(self):
                calls.append("generate")
                return result

            def generate_progressive(self, **kwargs):
                raise AssertionError("Top-N progressive preview must not be used.")

        screen._scheduling_presenter = FullGenerationPresenter()

        DateManagementScreen._handle_generate(screen)

        self.assertEqual(calls, ["generate"])


if __name__ == "__main__":
    unittest.main()
