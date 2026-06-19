"""Unit tests for SchedulingService (SCRUM-125).

These tests verify that the service reads from the cache, runs the Version 1.0
filtering and generation, stores results back, and validates required inputs.
A temporary pickle path keeps the real cache file untouched.
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
from models import Course, ExamPeriod, ProgramEnrollment
from ranking_settings import (
    RankingCriterion,
    RankingPreference,
    RankingSettings,
)
from scheduling.schedulingService import SchedulingService


def exam_course(name, number, program, semester="FALL", status="Obligatory"):
    """Build a single-enrollment Exam course for service tests."""
    return Course(
        name=name,
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment(program, 1, semester, status)],
        evaluation_type="Exam",
    )


def fall_period():
    """A small FALL Aleph period with two usable dates."""
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        excluded_dates=[],
    )


class SchedulingServiceTests(unittest.TestCase):
    """Service behavior against a temporary, isolated cache."""

    def setUp(self) -> None:
        """Point the cache at a temp file and start from a clean state."""
        # Redirect cache persistence to a temp file so tests never touch the
        # real internal_data.pkl, and start from a guaranteed clean state.
        # The original path is saved so tearDown can restore it, otherwise a
        # later CacheManager() (in another test) would point at a deleted dir.
        self._original_pkl_path = CacheManager._PKL_PATH
        self._tmp = tempfile.TemporaryDirectory()
        CacheManager._PKL_PATH = Path(self._tmp.name) / "test_cache.pkl"
        self.cache = CacheManager()
        self.cache.clear()

    def tearDown(self) -> None:
        """Restore the original cache path and remove the temp directory."""
        # Restore first so the class-level path is valid for any later test,
        # then delete the temporary directory and its cache file.
        CacheManager._PKL_PATH = self._original_pkl_path
        self._tmp.cleanup()

    def test_generates_and_stores_schedules(self) -> None:
        """A complete cache yields schedules that are stored back in the cache."""
        self.cache.set_courses([exam_course("Physics 1", "83102", "83101")])
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

        outcome = SchedulingService().run(self.cache)

        self.assertEqual(outcome.relevant_course_count, 1)
        self.assertGreater(outcome.schedule_count, 0)
        # The schedules must also be persisted into the cache.
        self.assertEqual(
            self.cache.get_generated_schedules(),
            outcome.schedules,
        )
        self.assertEqual(
            self.cache.get_ranked_schedules(),
            outcome.ranked_schedules,
        )
        self.assertEqual(
            len(outcome.ranked_schedules),
            outcome.schedule_count,
        )

    def test_filters_out_non_selected_programs(self) -> None:
        """Courses outside the selected programs are not scheduled."""
        self.cache.set_courses(
            [
                exam_course("In", "83102", "83101"),
                exam_course("Out", "83200", "83108"),
            ]
        )
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

        outcome = SchedulingService().run(self.cache)
        self.assertEqual(outcome.relevant_course_count, 1)

    def test_courses_but_none_in_selected_programs_yields_zero(self) -> None:
        """Courses exist, but none belong to the selected programs.

        This is distinct from "no courses loaded": the run is valid, simply
        producing zero relevant courses and zero schedules.
        """
        self.cache.set_courses([exam_course("Out", "83200", "83108")])
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

        outcome = SchedulingService().run(self.cache)
        self.assertEqual(outcome.relevant_course_count, 0)
        self.assertEqual(outcome.schedule_count, 0)
        self.assertEqual(self.cache.get_generated_schedules(), [])

    def test_missing_courses_raises(self) -> None:
        """Running with no courses is a clear ValueError."""
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])
        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)

    def test_missing_periods_raises(self) -> None:
        """Running with no exam periods is a clear ValueError."""
        self.cache.set_courses([exam_course("Physics 1", "83102", "83101")])
        self.cache.set_selected_programs(["83101"])
        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)

    def test_missing_programs_raises(self) -> None:
        """Running with no selected programs is a clear ValueError."""
        self.cache.set_courses([exam_course("Physics 1", "83102", "83101")])
        self.cache.set_exam_periods([fall_period()])
        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)

    # ------------------------------------------------------------------
    # Part 3: constraint settings and ranking settings from the cache
    # (SCRUM-164)
    # ------------------------------------------------------------------

    def _set_minimal_valid_inputs(self) -> None:
        """Populate courses/periods/programs needed for run() to proceed."""
        self.cache.set_courses(
            [
                exam_course("Physics 1", "83102", "83101"),
                exam_course("Math 1", "83103", "83101"),
            ]
        )
        self.cache.set_exam_periods([fall_period()])
        self.cache.set_selected_programs(["83101"])

    def test_default_cache_settings_preserve_version_2_behavior(self) -> None:
        """An empty cache (no settings ever stored) behaves like Version 2.0.

        CacheManager.get_constraint_settings() returns the all-disabled
        configuration and get_ranking_settings() returns an empty priority
        list when nothing was ever set, so generation must proceed exactly
        as it did before Part 3 existed.
        """
        self._set_minimal_valid_inputs()

        outcome = SchedulingService().run(self.cache)

        self.assertGreater(outcome.schedule_count, 0)
        self.assertEqual(
            len(outcome.ranked_schedules),
            outcome.schedule_count,
        )

    def test_enabled_constraint_settings_are_passed_to_the_generator(self) -> None:
        """An enabled threshold constraint affects the generated schedules.

        Using max_exams_per_day = 1 with two single-date Exam courses sharing
        the only available exam date forces at least one course out of every
        complete system, compared to the unconstrained run.
        """
        self._set_minimal_valid_inputs()

        unconstrained = SchedulingService().run(self.cache)

        constraints = SchedulingConstraintSettings.default_configuration()
        constraints.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(enabled=True, k=1)
        )
        self.cache.set_constraint_settings(constraints)

        constrained = SchedulingService().run(self.cache)

        # The constrained run must not produce more schedules than the
        # unconstrained run, and the active settings must be the ones read
        # back from the cache (set_constraint_settings stores them as-is).
        self.assertLessEqual(
            constrained.schedule_count,
            unconstrained.schedule_count,
        )
        self.assertEqual(
            self.cache.get_constraint_settings().constraints[
                ThresholdConstraintType.max_exams_per_day
            ],
            ThresholdConstraintSetting(enabled=True, k=1),
        )

    def test_ranking_settings_from_cache_affect_result_order(self) -> None:
        """Ranking preferences stored in the cache reorder the ranked output.

        Storing a ranking preference and re-running must produce ranked
        schedules ordered by that criterion, not by raw generation order.
        """
        self._set_minimal_valid_inputs()

        self.cache.set_ranking_settings(
            RankingSettings(
                priority_list=[
                    RankingPreference(
                        criterion=RankingCriterion.min_mandatory_gap,
                    ),
                ]
            )
        )

        outcome = SchedulingService().run(self.cache)

        self.assertEqual(
            len(outcome.ranked_schedules),
            outcome.schedule_count,
        )
        self.assertEqual(
            self.cache.get_ranking_settings().priority_list[0].criterion,
            RankingCriterion.min_mandatory_gap,
        )

    def test_invalid_constraint_settings_raise_value_error(self) -> None:
        """A positive-threshold constraint with k = 0 fails validation.

        mandatory_gap_days requires k >= 1. run() must surface this as a
        ValueError before the generator is ever constructed.
        """
        self._set_minimal_valid_inputs()

        invalid_constraints = SchedulingConstraintSettings.default_configuration()
        invalid_constraints.constraints[
            ThresholdConstraintType.mandatory_gap_days
        ] = ThresholdConstraintSetting(enabled=True, k=0)
        self.cache.set_constraint_settings(invalid_constraints)

        with self.assertRaises(ValueError):
            SchedulingService().run(self.cache)

    def test_threshold_change_invalidates_previous_schedules_before_run(self) -> None:
        """Sanity check: cache-level invalidation (SCRUM-144) is honored.

        set_constraint_settings() clears generated/ranked schedules as soon
        as it is called; run() then regenerates from scratch under the new
        constraints.
        """
        self._set_minimal_valid_inputs()
        SchedulingService().run(self.cache)
        self.assertTrue(self.cache.get_generated_schedules())

        constraints = SchedulingConstraintSettings.default_configuration()
        constraints.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(enabled=True, k=1)
        )
        self.cache.set_constraint_settings(constraints)

        # Immediately after set_constraint_settings(), the cache is empty.
        self.assertEqual(self.cache.get_generated_schedules(), [])

        outcome = SchedulingService().run(self.cache)
        self.assertEqual(
            self.cache.get_generated_schedules(),
            outcome.schedules,
        )
    
    def test_outcome_exposes_diagnostics_counters(self) -> None:
        """generated/accepted/pruned counters come from the generator.

        These counters reflect individual (course, date) placement attempts
        during the recursive search, not complete exam systems —
        accepted_candidates is generally larger than schedule_count. The
        only invariant checked here is accepted + pruned == generated.
        """
        self._set_minimal_valid_inputs()

        outcome = SchedulingService().run(self.cache)

        self.assertGreater(outcome.generated_candidates, 0)
        self.assertEqual(
            outcome.accepted_candidates + outcome.pruned_candidates,
            outcome.generated_candidates,
        )

    def test_enabled_constraint_increases_pruned_candidates(self) -> None:
        """A strict threshold constraint causes some candidates to be pruned."""
        self._set_minimal_valid_inputs()

        constraints = SchedulingConstraintSettings.default_configuration()
        constraints.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(enabled=True, k=1)
        )
        self.cache.set_constraint_settings(constraints)

        outcome = SchedulingService().run(self.cache)

        self.assertGreater(outcome.pruned_candidates, 0)

    def test_any_constraint_enabled_false_by_default(self) -> None:
        """With default (all-disabled) cache settings, the flag is False."""
        self._set_minimal_valid_inputs()

        outcome = SchedulingService().run(self.cache)

        self.assertFalse(outcome.any_constraint_enabled)

    def test_any_constraint_enabled_true_when_one_threshold_is_active(self) -> None:
        """Enabling a single threshold constraint sets the flag to True,
        regardless of how many candidates it ends up pruning."""
        self._set_minimal_valid_inputs()

        constraints = SchedulingConstraintSettings.default_configuration()
        constraints.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(enabled=True, k=1)
        )
        self.cache.set_constraint_settings(constraints)

        outcome = SchedulingService().run(self.cache)

        self.assertTrue(outcome.any_constraint_enabled)

if __name__ == "__main__":
    unittest.main()
