"""Unit tests for SchedulingPresenter (SCRUM-125).

These tests verify the presenter turns service outcomes into display-ready
results, without a GUI. A fake service is injected so the presenter is tested in
isolation from the real scheduling engine.
"""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from gui.presenters.schedulingPresenter import SchedulingPresenter
from scheduling.schedulingService import SchedulingOutcome


class _FakeService:
    """Stand-in for SchedulingService returning a scripted outcome or error."""

    def __init__(self, outcome=None, error=None):
        """Store a scripted outcome to return, or an error to raise."""
        self._outcome = outcome
        self._error = error
        self.run_kwargs = None

    def run(self, cache, **_kwargs):
        """Mimic SchedulingService.run: raise the scripted error or return
        the scripted outcome, ignoring the cache argument."""
        self.run_kwargs = _kwargs
        if self._error is not None:
            raise self._error
        return self._outcome


class SchedulingPresenterTests(unittest.TestCase):
    """Presenter translation of service results into user-facing messages."""

    def test_success_reports_schedule_count(self) -> None:
        """A non-empty outcome becomes a success result carrying the count."""
        service = _FakeService(
            outcome=SchedulingOutcome(
                relevant_course_count=2,
                schedule_count=5,
                schedules=[object()] * 5,
            )
        )
        presenter = SchedulingPresenter(cache=object(), service=service)
        result = presenter.generate()
        self.assertTrue(result.success)
        self.assertEqual(result.schedule_count, 5)
        self.assertEqual(result.displayed_count, 5)
        self.assertEqual(
            service.run_kwargs,
            {"rank_results": False, "allow_fallback": True},
        )

    def test_zero_schedules_is_success_with_explanation(self) -> None:
        """Zero systems is still a success, with an explanatory message."""
        service = _FakeService(
            outcome=SchedulingOutcome(
                relevant_course_count=2,
                schedule_count=0,
                schedules=[],
            )
        )
        presenter = SchedulingPresenter(cache=object(), service=service)
        result = presenter.generate()
        # No systems is not a crash: success True, count 0, explanatory message.
        self.assertTrue(result.success)
        self.assertEqual(result.schedule_count, 0)

    def test_zero_with_no_relevant_courses_has_program_focused_message(self) -> None:
        """Zero systems AND zero relevant courses points the user at programs."""
        service = _FakeService(
            outcome=SchedulingOutcome(
                relevant_course_count=0,
                schedule_count=0,
                schedules=[],
            )
        )
        presenter = SchedulingPresenter(cache=object(), service=service)
        result = presenter.generate()
        self.assertTrue(result.success)
        # Message must mention programs, not date exclusions, in this case.
        self.assertIn("programs", result.message)
        self.assertNotIn("excluding", result.message)
    
    def test_zero_with_constraint_enabled_has_constraint_focused_message(self) -> None:
        """Zero systems while a Part 3 threshold constraint is active points
        at constraints, regardless of the raw pruned_candidates count.

        any_constraint_enabled — not pruned_candidates — drives this branch,
        since pruned_candidates is also incremented by the always-active
        base conflict rule and is therefore not a reliable signal on its own
        (SCRUM-164 audit finding).
        """
        service = _FakeService(
            outcome=SchedulingOutcome(
                relevant_course_count=2,
                schedule_count=0,
                schedules=[],
                generated_candidates=10,
                accepted_candidates=0,
                pruned_candidates=10,
                any_constraint_enabled=True,
            )
        )
        presenter = SchedulingPresenter(cache=object(), service=service)
        result = presenter.generate()

        self.assertTrue(result.success)
        self.assertEqual(result.schedule_count, 0)
        self.assertIn("constraint", result.message.lower())

    def test_zero_without_constraint_enabled_keeps_date_focused_message(self) -> None:
        """Zero systems with no Part 3 constraint active keeps the original
        date-focused message, even if pruned_candidates > 0.

        This is the regression guard for the audit finding: a pure V1.0/V2.0
        conflict (base rule only, no Part 3 constraint enabled) must NOT
        produce the "relax a threshold constraint" message.
        """
        service = _FakeService(
            outcome=SchedulingOutcome(
                relevant_course_count=2,
                schedule_count=0,
                schedules=[],
                generated_candidates=2,
                accepted_candidates=0,
                pruned_candidates=2,
                any_constraint_enabled=False,
            )
        )
        presenter = SchedulingPresenter(cache=object(), service=service)
        result = presenter.generate()

        self.assertTrue(result.success)
        self.assertIn("excluding", result.message)
        self.assertNotIn("constraint", result.message.lower())

    def test_unexpected_exception_becomes_failure_not_crash(self) -> None:
        """A non-ValueError from the service is caught, not propagated."""
        service = _FakeService(error=MemoryError("boom"))
        presenter = SchedulingPresenter(cache=object(), service=service)
        # Must not raise; should return a failure result instead.
        result = presenter.generate()
        self.assertFalse(result.success)
        self.assertIn("MemoryError", result.message)

    def test_value_error_becomes_failure_message(self) -> None:
        """A service ValueError is turned into a failure result, not raised."""
        service = _FakeService(error=ValueError("No courses loaded."))
        presenter = SchedulingPresenter(cache=object(), service=service)
        result = presenter.generate()
        self.assertFalse(result.success)
        self.assertIn("No courses loaded.", result.message)


if __name__ == "__main__":
    unittest.main()
