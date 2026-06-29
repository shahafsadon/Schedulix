"""Integration test: real SchedulingService + SchedulingPresenter, no fakes
(SCRUM-164 audit follow-up).

The unit tests for SchedulingPresenter use a _FakeService with hand-set
SchedulingOutcome fields, which validated the presenter's branching logic
but could not catch a mismatch between what the real generator produces and
what the presenter expects. This test exercises the real
ExamScheduleGenerator -> SchedulingService -> SchedulingPresenter chain for
the two zero-result cases that the message routing must distinguish:

1. Zero result caused by date/conflict availability alone, with no Part 3
   threshold constraint enabled -> date-focused message (pre-Part-3
   behavior, must be preserved).
2. Zero strict result while a Part 3 threshold constraint is enabled ->
   normal GUI generation offers a clearly marked compromise schedule when a
   hard-valid fallback exists.
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from application.cache_manager import CacheManager
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from gui.presenters.schedulingPresenter import SchedulingPresenter
from models import Course, ExamPeriod, ProgramEnrollment


def mandatory_course(name, number, program):
    """A single-enrollment Obligatory Exam course."""
    return Course(
        name=name,
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment(program, 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def single_date_period():
    """A FALL Aleph period with exactly one usable date.

    Two mandatory courses sharing this single date is the classic V1.0/V2.0
    "no conflict-free arrangement fits" zero-result case, with no Part 3
    constraint involved.
    """
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        excluded_dates=[],
    )


def two_date_period():
    """A FALL Aleph period with two usable dates, enough for the base
    conflict rule to find a non-empty result without any Part 3 constraint."""
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        excluded_dates=[],
    )


class SchedulingServicePresenterFlowTests(unittest.TestCase):
    """Real generator + service + presenter, no fakes."""

    def setUp(self) -> None:
        """Point the cache at a temp file and start from a clean state."""
        self._original_pkl_path = CacheManager._PKL_PATH
        self._tmp = tempfile.TemporaryDirectory()
        CacheManager._PKL_PATH = Path(self._tmp.name) / "test_cache.pkl"
        self.cache = CacheManager()
        self.cache.clear()

    def tearDown(self) -> None:
        """Restore the original cache path and remove the temp directory."""
        CacheManager._PKL_PATH = self._original_pkl_path
        self._tmp.cleanup()

    def test_zero_result_from_base_conflict_alone_gives_date_focused_message(
        self,
    ) -> None:
        """Two mandatory courses sharing the only available date, with no
        Part 3 constraint enabled, must give the pre-Part-3 date-focused
        message — not the "relax a threshold constraint" message.

        This is the exact scenario the audit identified as a regression:
        the base conflict rule alone prunes candidates, but
        any_constraint_enabled is False.
        """
        self.cache.set_courses(
            [
                mandatory_course("Physics 1", "83102", "83101"),
                mandatory_course("Math 1", "83103", "83101"),
            ]
        )
        self.cache.set_exam_periods([single_date_period()])
        self.cache.set_selected_programs(["83101"])
        # Default cache state: all constraints disabled (no set_constraint_settings call).

        presenter = SchedulingPresenter(cache=self.cache)
        result = presenter.generate()

        self.assertTrue(result.success)
        self.assertEqual(result.schedule_count, 0)
        self.assertIn("excluding", result.message)
        self.assertNotIn("constraint", result.message.lower())

    def test_zero_result_with_constraint_enabled_offers_fallback_schedule(
        self,
    ) -> None:
        """The same two-course setup, but with two usable dates so the base
        rule alone would succeed, and max_exams_per_day = 1 enabled.

        With k = 1 and two mandatory exams needing two different days, the
        constraint forces zero strict complete systems while any_constraint_enabled
        is True. The normal GUI generation path should then offer a fallback
        schedule that still respects hard constraints.
        """
        self.cache.set_courses(
            [
                mandatory_course("Physics 1", "83102", "83101"),
                mandatory_course("Math 1", "83103", "83101"),
            ]
        )
        self.cache.set_exam_periods([two_date_period()])
        self.cache.set_selected_programs(["83101"])

        constraints = SchedulingConstraintSettings.default_configuration()
        constraints.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(enabled=True, k=1)
        )
        # k=1 alone does not force zero (each date can host 1 exam, and there
        # are 2 dates for 2 courses). Add mandatory_gap_days with a large k to
        # guarantee zero complete systems while keeping any_constraint_enabled
        # True via at least one enabled constraint.
        constraints.constraints[ThresholdConstraintType.mandatory_gap_days] = (
            ThresholdConstraintSetting(enabled=True, k=30)
        )
        self.cache.set_constraint_settings(constraints)

        presenter = SchedulingPresenter(cache=self.cache)
        result = presenter.generate()

        self.assertTrue(result.success)
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.schedule_count, 1)
        self.assertIn("Fallback schedule", result.message)
        self.assertEqual(len(self.cache.get_generated_schedules()), 1)
        self.assertEqual(len(self.cache.get_ranked_schedules()), 1)
        self.assertTrue(self.cache.get_ranked_schedules()[0].is_fallback)


if __name__ == "__main__":
    unittest.main()
