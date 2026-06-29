"""Unit tests for ScheduleNavigationPresenter (SCRUM-126).

These tests verify navigation state, display-ready schedule data, Part 4
snapshot actions, manual moves, and undo/redo behavior without any GUI.
"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import ExamPeriod
from models import Course, ProgramEnrollment
from ranking_settings import (
    RankedExamSystem,
    RankingCriterion,
    RankingPreference,
    RankingSettings,
    ScheduleMetrics,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from scheduling.qualityTagCalculator import ScheduleQualityTag
from scheduling.scheduleIntrospection import flatten_exam_system
from gui.presenters.scheduleNavigationPresenter import (
    ResultMode,
    ScheduleNavigationPresenter,
)


def make_exam(name, number, exam_date, status="Obligatory"):
    """Build a ScheduledExam for navigation tests."""
    course = Course(
        name=name,
        course_number=number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", status)],
        evaluation_type="Exam",
    )
    return ScheduledExam(course=course, exam_date=exam_date)


def make_system(semester="FALL", moed="Aleph", exams=None):
    """Build a one-period ExamSystem for navigation tests."""
    return ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester=semester,
                moed=moed,
                scheduled_exams=exams or [],
            )
        ]
    )


def make_ranked(
    system,
    key,
    min_gap=0,
    average_gap=0.0,
    elective_collisions=0,
    mandatory_span=0,
    max_exams_per_day=1,
    penalty_score=None,
    penalty_details=(),
    is_fallback=False,
):
    """Wrap an ExamSystem with simple metrics for navigation tests."""
    return RankedExamSystem(
        exam_system=system,
        metrics=ScheduleMetrics(
            schedule_id=key,
            min_mandatory_gap=min_gap,
            average_all_gap=average_gap,
            elective_collision_count=elective_collisions,
            mandatory_span=mandatory_span,
            max_exams_per_day=max_exams_per_day,
        ),
        key=key,
        penalty_score=penalty_score,
        penalty_details=penalty_details,
        is_fallback=is_fallback,
    )


class FakeCache:
    """Small cache double for Part 4 presenter tests."""

    def __init__(
        self,
        settings=None,
        periods=None,
    ):
        self._settings = settings or SchedulingConstraintSettings.default_configuration()
        self._periods = periods or []

    def get_constraint_settings(self):
        """Return active constraint settings."""
        return self._settings

    def get_exam_periods(self):
        """Return available exam periods."""
        return self._periods


class ScheduleNavigationPresenterTests(unittest.TestCase):
    """Navigation and view-building behavior."""

    def test_empty_schedules_has_no_view(self) -> None:
        """With no systems, there is nothing to navigate or display."""
        presenter = ScheduleNavigationPresenter([])
        self.assertFalse(presenter.has_schedules())
        self.assertEqual(presenter.total(), 0)
        self.assertEqual(presenter.position(), 0)
        self.assertIsNone(presenter.current_view())

    def test_counter_starts_at_one_of_n(self) -> None:
        """The counter starts at system 1 of N."""
        presenter = ScheduleNavigationPresenter(
            [make_system(), make_system(), make_system()]
        )
        self.assertEqual(presenter.position(), 1)
        self.assertEqual(presenter.total(), 3)

    def test_counter_uses_full_generated_total_not_top_preview_limit(self) -> None:
        """Normal unranked navigation reports the real generated count."""
        presenter = ScheduleNavigationPresenter([make_system() for _ in range(75)])

        view = presenter.current_view()

        self.assertIsNotNone(view)
        self.assertEqual(presenter.position(), 1)
        self.assertEqual(presenter.total(), 75)
        self.assertEqual(view.total, 75)

    def test_next_and_previous_navigation(self) -> None:
        """Next advances and previous goes back within bounds."""
        presenter = ScheduleNavigationPresenter(
            [make_system(), make_system(), make_system()]
        )
        self.assertTrue(presenter.can_go_next())
        self.assertFalse(presenter.can_go_previous())

        presenter.next()
        self.assertEqual(presenter.position(), 2)
        self.assertTrue(presenter.can_go_previous())

        presenter.previous()
        self.assertEqual(presenter.position(), 1)

    def test_navigation_does_not_go_out_of_bounds(self) -> None:
        """Previous at the start and next at the end are no-ops."""
        presenter = ScheduleNavigationPresenter([make_system(), make_system()])
        # Already at first: previous stays put.
        presenter.previous()
        self.assertEqual(presenter.position(), 1)
        # Move to last, then next stays put.
        presenter.next()
        self.assertEqual(presenter.position(), 2)
        self.assertFalse(presenter.can_go_next())
        presenter.next()
        self.assertEqual(presenter.position(), 2)

    def test_current_view_exposes_sections_and_exams(self) -> None:
        """The view groups exams under their semester/moed section."""
        system = make_system(
            exams=[
                make_exam("Calculus 1", "83112", date(2026, 2, 1)),
                make_exam("Physics 1", "83102", date(2026, 1, 29)),
            ]
        )
        presenter = ScheduleNavigationPresenter([system])
        view = presenter.current_view()

        self.assertEqual(view.position, 1)
        self.assertEqual(view.total, 1)
        self.assertEqual(len(view.sections), 1)
        section = view.sections[0]
        self.assertEqual(section.semester, "FALL")
        self.assertEqual(section.moed, "Aleph")
        # Exams sorted by date: Physics (29-01) before Calculus (01-02).
        self.assertEqual(section.exams[0].course_name, "Physics 1")
        self.assertEqual(section.exams[0].exam_date, "29-01-2026")
        self.assertEqual(section.exams[1].course_name, "Calculus 1")

    def test_current_system_returns_the_displayed_raw_system(self) -> None:
        """Export can ask for the currently displayed system without private access."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        presenter = ScheduleNavigationPresenter([first, second])

        self.assertIs(presenter.current_system(), first)

        presenter.next()

        self.assertIs(presenter.current_system(), second)

    def test_sections_sorted_by_semester_then_moed(self) -> None:
        """Sections follow the FALL/SPRI and Aleph/Bet ordering."""
        system = ExamSystem(
            period_schedules=[
                ExamSchedule(semester="SPRI", moed="Aleph", scheduled_exams=[]),
                ExamSchedule(semester="FALL", moed="Bet", scheduled_exams=[]),
                ExamSchedule(semester="FALL", moed="Aleph", scheduled_exams=[]),
            ]
        )
        presenter = ScheduleNavigationPresenter([system])
        order = [(s.semester, s.moed) for s in presenter.current_view().sections]
        self.assertEqual(
            order,
            [("FALL", "Aleph"), ("FALL", "Bet"), ("SPRI", "Aleph")],
        )

    def test_exam_row_exposes_status(self) -> None:
        """Each exam row carries the course requirement status."""
        system = make_system(
            exams=[make_exam("Elective C", "83200", date(2026, 1, 1), status="Elective")]
        )
        presenter = ScheduleNavigationPresenter([system])
        row = presenter.current_view().sections[0].exams[0]
        self.assertEqual(row.status, "Elective")

    def test_exam_row_exposes_program_numbers(self) -> None:
        """Each exam row carries the program(s) the course belongs to."""
        course = Course(
            name="Cross",
            course_number="83555",
            instructor="Dr. Test",
            programs=[
                ProgramEnrollment("83101", 1, "FALL", "Obligatory"),
                ProgramEnrollment("83108", 1, "FALL", "Elective"),
            ],
            evaluation_type="Exam",
        )
        exam = ScheduledExam(course=course, exam_date=date(2026, 1, 29))
        system = ExamSystem(
            period_schedules=[
                ExamSchedule("FALL", "Aleph", [exam])
            ]
        )
        presenter = ScheduleNavigationPresenter([system])
        row = presenter.current_view().sections[0].exams[0]
        self.assertEqual(row.program_numbers, "83101, 83108")

    def test_calendar_year_is_taken_from_exam_dates(self) -> None:
        """calendar_year reflects the smallest year present in the system."""
        system = make_system(
            exams=[
                make_exam("A", "83001", date(2026, 1, 29)),
                make_exam("B", "83002", date(2026, 2, 1)),
            ]
        )
        presenter = ScheduleNavigationPresenter([system])
        self.assertEqual(presenter.current_view().calendar_year, 2026)

    def test_exams_by_iso_date_indexes_each_exam_day(self) -> None:
        """The iso-date index lets the calendar look up exams in O(1)."""
        e1 = make_exam("Physics 1", "83102", date(2026, 1, 29))
        e2 = make_exam("Calculus 1", "83112", date(2026, 1, 29))
        e3 = make_exam("Algo", "83120", date(2026, 2, 5))
        system = ExamSystem(
            period_schedules=[ExamSchedule("FALL", "Aleph", [e1, e2, e3])]
        )
        presenter = ScheduleNavigationPresenter([system])
        index = presenter.current_view().exams_by_iso_date
        # Two exams on Jan 29, one on Feb 5.
        self.assertEqual(len(index["2026-01-29"]), 2)
        self.assertEqual(len(index["2026-02-05"]), 1)
        # Days without exams are not present.
        self.assertNotIn("2026-01-30", index)

    def test_relevant_months_spans_all_systems(self) -> None:
        """relevant_months collects exam months across every system, sorted."""
        s1 = make_system(exams=[make_exam("A", "83001", date(2026, 1, 29))])
        s2 = make_system(exams=[make_exam("B", "83002", date(2026, 3, 5))])
        presenter = ScheduleNavigationPresenter([s1, s2])
        # January and March appear; February (no exam) does not.
        self.assertEqual(presenter.relevant_months(), [(2026, 1), (2026, 3)])

    def test_relevant_months_empty_when_no_schedules(self) -> None:
        """With no systems there are no months to draw."""
        self.assertEqual(ScheduleNavigationPresenter([]).relevant_months(), [])

    def test_ranked_input_exposes_metrics_summary(self) -> None:
        """Ranked wrappers let the view display calculated metric values."""
        system = make_system(
            exams=[make_exam("A", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(
                    system,
                    key=4,
                    min_gap=7,
                    average_gap=4.5,
                    elective_collisions=2,
                    mandatory_span=10,
                    max_exams_per_day=3,
                )
            ]
        )

        metrics = presenter.current_view().metrics_summary

        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.schedule_id, 4)
        self.assertEqual(metrics.min_mandatory_gap, 7)
        self.assertEqual(metrics.average_all_gap, 4.5)
        self.assertEqual(metrics.elective_collision_count, 2)
        self.assertEqual(metrics.mandatory_span, 10)
        self.assertEqual(metrics.max_exams_per_day, 3)

    def test_apply_ranked_schedules_preserves_current_system_when_possible(self) -> None:
        """Re-ranking keeps the selected system even when its position changes."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        first_ranked = make_ranked(first, key=1)
        second_ranked = make_ranked(second, key=2)
        presenter = ScheduleNavigationPresenter([first_ranked, second_ranked])
        presenter.next()

        presenter.apply_ranked_schedules([second_ranked, first_ranked])

        self.assertIs(presenter.current_system(), second)
        self.assertEqual(presenter.position(), 1)

    def test_apply_ranking_uses_generated_source_even_when_ranked_view_exists(self) -> None:
        """Ranking changes must not use the previous ranked preview as input."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        first_ranked = make_ranked(first, key=1, min_gap=2)
        second_ranked = make_ranked(second, key=2, min_gap=9)

        class FakeRankingService:
            def __init__(self):
                self.generated_source = None

            def rank_generated_schedules(self, schedules, ranking_settings):
                self.generated_source = list(schedules)
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": [
                            make_ranked(second, key=2, min_gap=9),
                            make_ranked(first, key=1, min_gap=2),
                        ],
                        "elapsed_seconds": 0.25,
                    },
                )()

            def rerank(self, ranked_schedules, ranking_settings):
                raise AssertionError("Ranking changes must not rerank only the preview.")

        service = FakeRankingService()
        presenter = ScheduleNavigationPresenter(
            [first_ranked, second_ranked],
            cache_manager=_RecordingRankingCache(
                generated_schedules=[first, second],
            ),
        )

        result = presenter.apply_ranking(
            RankingSettings(
                [
                    RankingPreference(
                        RankingCriterion.min_mandatory_gap,
                    )
                ]
            ),
            ranking_service=service,
        )

        self.assertTrue(result.success)
        self.assertEqual(presenter.result_mode, ResultMode.FINAL_RANKED)
        self.assertEqual(service.generated_source, [first, second])
        self.assertIs(presenter.current_system(), second)
        self.assertEqual(presenter.position(), 1)
        self.assertEqual(
            presenter.current_view().exams_by_iso_date["2026-01-02"][0].course_name,
            "Second",
        )
        self.assertEqual(
            presenter.current_view().metrics_summary.min_mandatory_gap,
            9,
        )

        presenter.next()

        self.assertIs(presenter.current_system(), first)
        self.assertEqual(
            presenter.current_view().exams_by_iso_date["2026-01-01"][0].course_name,
            "First",
        )
        self.assertEqual(
            presenter.current_view().metrics_summary.min_mandatory_gap,
            2,
        )

    def test_apply_ranking_navigation_uses_ranked_order_not_original_neighbors(self) -> None:
        """Next/Previous in ranked mode walks the ranked view, not generated indexes."""
        systems = [
            make_system(
                exams=[
                    make_exam(
                        f"Course {index}",
                        f"83{index:03d}",
                        date(2026, 1, 1),
                    )
                ]
            )
            for index in range(60)
        ]
        ranked_order = [
            systems[55],
            systems[2],
            *systems[:2],
            *systems[3:55],
            *systems[56:],
        ]
        cache = _RecordingRankingCache(generated_schedules=systems)

        class FakeRankingService:
            def rank_generated_schedules(self, schedules, ranking_settings):
                self.generated_source = list(schedules)
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": [
                            make_ranked(system, key=systems.index(system) + 1)
                            for system in ranked_order
                        ],
                        "elapsed_seconds": 0.0,
                    },
                )()

            def rerank(self, *_args):
                raise AssertionError("Should not rerank only the ranked preview.")

        service = FakeRankingService()
        presenter = ScheduleNavigationPresenter(
            systems,
            cache_manager=cache,
        )

        result = presenter.apply_ranking(
            RankingSettings(
                [RankingPreference(RankingCriterion.average_all_gap)]
            ),
            ranking_service=service,
        )

        self.assertTrue(result.success)
        self.assertEqual(len(service.generated_source), 60)
        self.assertEqual(len(cache.get_generated_schedules()), 60)
        self.assertEqual(presenter.total(), 60)
        self.assertEqual(presenter.position(), 1)
        self.assertIs(presenter.current_system(), systems[55])

        presenter.next()

        self.assertEqual(presenter.position(), 2)
        self.assertIs(presenter.current_system(), systems[2])
        self.assertIsNot(presenter.current_system(), systems[56])

    def test_progressive_ranking_preview_navigation_uses_ranked_order(self) -> None:
        """Live Top-50 updates should navigate within the ranked preview order."""
        systems = [
            make_system(
                exams=[
                    make_exam(
                        f"Course {index}",
                        f"83{index:03d}",
                        date(2026, 1, 1),
                    )
                ]
            )
            for index in range(60)
        ]
        cache = _RecordingRankingCache(generated_schedules=systems)

        class FakeProgressiveRankingService:
            def rank_generated_batch(
                self,
                schedules,
                ranking_settings,
                starting_schedule_id,
            ):
                scores = {id(systems[55]): 1000.0, id(systems[2]): 999.0}
                ranked = [
                    make_ranked(
                        system,
                        key=starting_schedule_id + index,
                        average_gap=scores.get(
                            id(system),
                            float(100 - systems.index(system)),
                        ),
                    )
                    for index, system in enumerate(schedules)
                ]
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": ranked,
                        "elapsed_seconds": 0.0,
                    },
                )()

        presenter = ScheduleNavigationPresenter(
            systems,
            cache_manager=cache,
        )
        final_update = presenter.rank_progressively(
            RankingSettings(
                [RankingPreference(RankingCriterion.average_all_gap)]
            ),
            run_id=1,
            ranking_service=FakeProgressiveRankingService(),
            batch_size=13,
            preview_limit=50,
            min_update_interval_seconds=0,
        )

        presenter.update_schedules(
            final_update.ranked_schedules,
            is_partial=False,
            systems_seen=final_update.total_count,
            displayed_count=final_update.displayed_count,
        )

        self.assertEqual(final_update.total_count, 60)
        self.assertEqual(presenter.total(), 60)
        self.assertEqual(presenter.position(), 1)
        self.assertIs(presenter.current_system(), systems[55])

        presenter.next()

        self.assertEqual(presenter.position(), 2)
        self.assertIs(presenter.current_system(), systems[2])
        self.assertIsNot(presenter.current_system(), systems[56])

    def test_apply_empty_ranking_restores_generation_order_by_key(self) -> None:
        """Removing all criteria restores the original generated order."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        first_ranked = make_ranked(first, key=1)
        second_ranked = make_ranked(second, key=2)
        presenter = ScheduleNavigationPresenter(
            [second_ranked, first_ranked],
            cache_manager=_RecordingRankingCache(generated_schedules=[first, second]),
        )

        result = presenter.apply_ranking(RankingSettings([]))

        self.assertTrue(result.success)
        self.assertEqual(presenter.result_mode, ResultMode.FINAL_RANKED)
        self.assertIs(presenter.current_system(), first)
        self.assertEqual(presenter.position(), 1)

        presenter.next()

        self.assertIs(presenter.current_system(), second)

    def test_changing_ranking_criteria_updates_current_metrics_to_new_top_result(self) -> None:
        """Apply Ranking reorders by the new criterion and exposes matching metrics."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        first_ranked = make_ranked(
            first,
            key=1,
            min_gap=10,
            average_gap=3.0,
            elective_collisions=0,
            mandatory_span=8,
            max_exams_per_day=1,
        )
        second_ranked = make_ranked(
            second,
            key=2,
            min_gap=4,
            average_gap=9.0,
            elective_collisions=2,
            mandatory_span=12,
            max_exams_per_day=3,
        )

        class FakeRankingService:
            def rank_generated_schedules(self, schedules, ranking_settings):
                ranked = [first_ranked, second_ranked]
                if ranking_settings.priority_list[0].criterion == (
                    RankingCriterion.average_all_gap
                ):
                    ranked = [second_ranked, first_ranked]
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": ranked,
                        "elapsed_seconds": 0.0,
                    },
                )()

            def rerank(self, *_args):
                raise AssertionError("Should not rerank a previous ranked preview.")

        ranking_service = FakeRankingService()
        presenter = ScheduleNavigationPresenter(
            [first_ranked, second_ranked],
            cache_manager=_RecordingRankingCache(generated_schedules=[first, second]),
        )

        presenter.apply_ranking(
            RankingSettings(
                [RankingPreference(RankingCriterion.min_mandatory_gap)]
            ),
            ranking_service=ranking_service,
        )
        first_metrics = presenter.current_view().metrics_summary
        self.assertEqual(first_metrics.schedule_id, 1)
        self.assertEqual(first_metrics.min_mandatory_gap, 10)

        presenter.apply_ranking(
            RankingSettings(
                [RankingPreference(RankingCriterion.average_all_gap)]
            ),
            ranking_service=ranking_service,
        )
        second_metrics = presenter.current_view().metrics_summary

        self.assertEqual(second_metrics.schedule_id, 2)
        self.assertEqual(second_metrics.average_all_gap, 9.0)
        self.assertEqual(second_metrics.elective_collision_count, 2)
        self.assertEqual(second_metrics.mandatory_span, 12)
        self.assertEqual(second_metrics.max_exams_per_day, 3)

    def test_active_ranking_from_workflow_applies_to_live_updates(self) -> None:
        """Incoming live batches honour ranking restored by the workflow."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        settings = RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        )
        presenter = ScheduleNavigationPresenter(
            [],
            active_ranking=settings,
        )

        presenter.update_schedules(
            [
                make_ranked(first, key=1, min_gap=2),
                make_ranked(second, key=2, min_gap=9),
            ],
            is_partial=True,
            systems_seen=2,
            displayed_count=2,
        )

        self.assertIs(presenter.current_system(), second)
        self.assertEqual(presenter.result_mode, ResultMode.LIVE_RANKED_PREVIEW)

    def test_progressive_ranking_emits_partial_top_preview_and_full_final(self) -> None:
        """Progressive ranking previews Top-N, then exposes the full ranked list."""
        systems = [
            make_system(
                exams=[
                    make_exam(
                        f"Course {index}",
                        f"83{index:03d}",
                        date(2026, 1, 1 + index),
                    )
                ]
            )
            for index in range(6)
        ]
        presenter = ScheduleNavigationPresenter(systems)
        updates = []

        final = presenter.rank_progressively(
            RankingSettings(
                [RankingPreference(RankingCriterion.max_exams_per_day)]
            ),
            run_id=7,
            on_update=updates.append,
            batch_size=2,
            preview_limit=3,
        )

        self.assertTrue(updates)
        self.assertTrue(updates[0].is_partial)
        self.assertLessEqual(updates[0].displayed_count, 3)
        self.assertFalse(final.is_partial)
        self.assertEqual(final.total_count, 6)
        self.assertEqual(final.displayed_count, 6)
        self.assertIn("Showing all 6", final.message)

        presenter.update_schedules(
            updates[0].ranked_schedules,
            is_partial=True,
            systems_seen=updates[0].processed_count,
            displayed_count=updates[0].displayed_count,
        )

        self.assertLessEqual(presenter.total(), 3)
        while presenter.can_go_next():
            presenter.next()
        self.assertEqual(presenter.position(), presenter.total())
        presenter.next()
        self.assertEqual(presenter.position(), presenter.total())

        presenter.update_schedules(
            final.ranked_schedules,
            is_partial=False,
            systems_seen=final.total_count,
            displayed_count=final.displayed_count,
        )

        self.assertEqual(presenter.total(), 6)
        self.assertEqual(presenter.position(), 1)

    def test_progressive_ranking_throttles_partial_updates(self) -> None:
        """Worker progress does not flood the Tk event queue every batch."""
        systems = [
            make_system(
                exams=[
                    make_exam(
                        f"Course {index}",
                        f"8{index:04d}",
                        date(2026, 1, 1 + index),
                    )
                ]
            )
            for index in range(8)
        ]
        presenter = ScheduleNavigationPresenter(systems)
        updates = []

        final = presenter.rank_progressively(
            RankingSettings(
                [RankingPreference(RankingCriterion.max_exams_per_day)]
            ),
            run_id=11,
            on_update=updates.append,
            batch_size=1,
            preview_limit=3,
            min_update_interval_seconds=0.5,
            clock=lambda: 10.0,
        )

        self.assertEqual(len(updates), 1)
        self.assertTrue(updates[0].is_partial)
        self.assertEqual(updates[0].processed_count, 1)
        self.assertFalse(final.is_partial)
        self.assertEqual(final.processed_count, 8)

    def test_live_update_preserves_current_ranked_identity_when_still_present(self) -> None:
        """Preview refresh keeps the same schedule when its key remains available."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        third = make_system(exams=[make_exam("Third", "83003", date(2026, 1, 3))])
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(first, key=1),
                make_ranked(second, key=2),
            ]
        )
        presenter.next()

        presenter.update_schedules(
            [
                make_ranked(third, key=3),
                make_ranked(second, key=2),
                make_ranked(first, key=1),
            ],
            is_partial=True,
            systems_seen=3,
            displayed_count=3,
        )

        self.assertIs(presenter.current_system(), second)
        self.assertEqual(presenter.position(), 2)

    def test_live_update_keeps_nearby_index_when_current_ranked_identity_disappears(self) -> None:
        """If a browsed preview item drops out of Top 50, keep navigation usable."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        third = make_system(exams=[make_exam("Third", "83003", date(2026, 1, 3))])
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(first, key=1),
                make_ranked(second, key=2),
            ]
        )
        presenter.next()

        presenter.update_schedules(
            [
                make_ranked(third, key=3),
                make_ranked(first, key=1),
            ],
            is_partial=True,
            systems_seen=3,
            displayed_count=2,
        )

        self.assertIs(presenter.current_system(), first)
        self.assertEqual(presenter.position(), 2)
        self.assertTrue(presenter.can_go_previous())
        self.assertFalse(presenter.can_go_next())

if __name__ == "__main__":
    unittest.main()


class _RecordingRankingCache:
    def __init__(self, generated_schedules=None) -> None:
        self.ranking_settings = None
        self.ranked_schedules = None
        self.set_ranked_calls = 0
        self.generated_schedules = list(generated_schedules or [])

    def get_generated_schedules(self):
        return list(self.generated_schedules)

    def set_ranking_settings(self, settings):
        self.ranking_settings = settings

    def set_ranked_schedules(self, ranked_schedules):
        self.set_ranked_calls += 1
        self.ranked_schedules = list(ranked_schedules)


class ScheduleNavigationPresenterCacheFinalizationTests(unittest.TestCase):
    """Cache behavior for ranking-only changes from the results screen."""

    def test_completed_ranking_change_persists_settings_and_ranked_order(self) -> None:
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        cache = _RecordingRankingCache(generated_schedules=[first, second])
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(first, key=1, min_gap=2),
                make_ranked(second, key=2, min_gap=9),
            ],
            cache_manager=cache,
        )
        settings = RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        )

        result = presenter.apply_ranking(settings)

        self.assertTrue(result.success)
        self.assertIs(cache.ranking_settings, settings)
        self.assertEqual(cache.set_ranked_calls, 1)
        self.assertEqual(cache.ranked_schedules, result.ranked_schedules)

    def test_partial_ranking_change_persists_settings_but_not_preview_results(self) -> None:
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        cache = _RecordingRankingCache(generated_schedules=[first, second])
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(first, key=1, min_gap=2),
                make_ranked(second, key=2, min_gap=9),
            ],
            cache_manager=cache,
        )
        presenter.update_schedules(
            [
                make_ranked(first, key=1, min_gap=2),
                make_ranked(second, key=2, min_gap=9),
            ],
            is_partial=True,
            systems_seen=2,
            displayed_count=2,
        )
        settings = RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        )

        result = presenter.apply_ranking(settings)

        self.assertTrue(result.success)
        self.assertIs(cache.ranking_settings, settings)
        self.assertEqual(cache.set_ranked_calls, 0)
        self.assertIsNone(cache.ranked_schedules)

    def test_ranking_change_without_full_generated_source_requires_regeneration(self) -> None:
        """Do not silently treat a persisted Top 50 preview as the full universe."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        cache = _RecordingRankingCache()
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(first, key=1, min_gap=2),
                make_ranked(second, key=2, min_gap=9),
            ],
            cache_manager=cache,
            result_mode=ResultMode.FINAL_RANKED,
        )

        result = presenter.apply_ranking(
            RankingSettings(
                [RankingPreference(RankingCriterion.min_mandatory_gap)]
            )
        )

        self.assertFalse(result.success)
        self.assertIn("Regenerate schedules", result.message)
        self.assertEqual(result.ranked_count, 2)
        self.assertEqual(cache.set_ranked_calls, 0)
        self.assertIsNone(cache.ranked_schedules)

    def test_later_ranking_change_uses_full_generated_cache_not_previous_top_50(self) -> None:
        systems = [
            make_system(
                exams=[
                    make_exam(
                        f"Course {index}",
                        f"83{index:03d}",
                        date(2026, 1, 1),
                    )
                ]
            )
            for index in range(60)
        ]
        previous_top_50 = [
            make_ranked(system, key=index + 1)
            for index, system in enumerate(systems[:50])
        ]
        cache = _RecordingRankingCache(generated_schedules=systems)

        class FakeRankingService:
            def __init__(self):
                self.received_count = 0

            def rank_generated_schedules(self, schedules, ranking_settings):
                source = list(schedules)
                self.received_count = len(source)
                ranked = [
                    make_ranked(system, key=index + 1, average_gap=float(index))
                    for index, system in enumerate(source)
                ]
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": list(reversed(ranked)),
                        "elapsed_seconds": 0.0,
                    },
                )()

            def rerank(self, *_args):
                raise AssertionError("Should not rerank the previous Top 50.")

        ranking_service = FakeRankingService()
        presenter = ScheduleNavigationPresenter(
            previous_top_50,
            cache_manager=cache,
            result_mode=ResultMode.FINAL_RANKED,
        )
        settings = RankingSettings(
            [RankingPreference(RankingCriterion.average_all_gap)]
        )

        result = presenter.apply_ranking(
            settings,
            ranking_service=ranking_service,
        )

        self.assertTrue(result.success)
        self.assertEqual(ranking_service.received_count, 60)
        self.assertEqual(len(cache.get_generated_schedules()), 60)
        self.assertEqual(cache.set_ranked_calls, 1)
        self.assertEqual(len(cache.ranked_schedules), 60)
        self.assertIs(presenter.current_system(), systems[59])

    def test_priority_change_uses_full_generated_cache_after_top_50_view(self) -> None:
        systems = self._numbered_systems(60)
        previous_top_50 = [
            make_ranked(system, key=index + 1, min_gap=1000 - index)
            for index, system in enumerate(systems[:50])
        ]
        cache = _RecordingRankingCache(generated_schedules=systems)

        class FakeRankingService:
            def __init__(self):
                self.calls = []

            def rank_generated_schedules(self, schedules, ranking_settings):
                source = list(schedules)
                self.calls.append(
                    (
                        len(source),
                        tuple(
                            preference.criterion
                            for preference in ranking_settings.priority_list
                        ),
                    )
                )
                ranked = [
                    make_ranked(
                        system,
                        key=index + 1,
                        min_gap=1000 - index,
                        average_gap=float(index),
                    )
                    for index, system in enumerate(source)
                ]
                if ranking_settings.priority_list[0].criterion == (
                    RankingCriterion.average_all_gap
                ):
                    ranked = list(reversed(ranked))
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": ranked,
                        "elapsed_seconds": 0.0,
                    },
                )()

            def rerank(self, *_args):
                raise AssertionError("Should not rerank the previous Top 50.")

        ranking_service = FakeRankingService()
        presenter = ScheduleNavigationPresenter(
            previous_top_50,
            cache_manager=cache,
            result_mode=ResultMode.FINAL_RANKED,
        )
        ranking_a = RankingSettings(
            [RankingPreference(RankingCriterion.min_mandatory_gap)]
        )
        ranking_b = RankingSettings(
            [
                RankingPreference(RankingCriterion.average_all_gap),
                RankingPreference(RankingCriterion.min_mandatory_gap),
            ]
        )

        first_result = presenter.apply_ranking(
            ranking_a,
            ranking_service=ranking_service,
        )
        second_result = presenter.apply_ranking(
            ranking_b,
            ranking_service=ranking_service,
        )

        self.assertTrue(first_result.success)
        self.assertTrue(second_result.success)
        self.assertEqual(
            ranking_service.calls,
            [
                (60, (RankingCriterion.min_mandatory_gap,)),
                (
                    60,
                    (
                        RankingCriterion.average_all_gap,
                        RankingCriterion.min_mandatory_gap,
                    ),
                ),
            ],
        )
        self.assertEqual(len(cache.get_generated_schedules()), 60)
        self.assertEqual(len(cache.ranked_schedules), 60)
        self.assertIs(presenter.current_system(), systems[59])

    def test_progressive_restart_uses_full_generated_source_not_current_preview(self) -> None:
        systems = self._numbered_systems(60)
        previous_top_50 = [
            make_ranked(system, key=index + 1, min_gap=1000 - index)
            for index, system in enumerate(systems[:50])
        ]
        cache = _RecordingRankingCache(generated_schedules=systems)

        class FakeProgressiveRankingService:
            def __init__(self):
                self.sources = []

            def rank_generated_batch(
                self,
                schedules,
                ranking_settings,
                starting_schedule_id,
            ):
                batch = list(schedules)
                self.sources.extend(batch)
                ranked = [
                    make_ranked(
                        system,
                        key=starting_schedule_id + index,
                        min_gap=10,
                        average_gap=float(systems.index(system)),
                        elective_collisions=systems.index(system),
                        mandatory_span=systems.index(system),
                        max_exams_per_day=systems.index(system),
                    )
                    for index, system in enumerate(batch)
                ]
                return type(
                    "Outcome",
                    (),
                    {
                        "ranked_schedules": ranked,
                        "elapsed_seconds": 0.0,
                    },
                )()

        presenter = ScheduleNavigationPresenter(
            previous_top_50,
            cache_manager=cache,
            result_mode=ResultMode.FINAL_RANKED,
        )
        settings = RankingSettings(
            [
                RankingPreference(RankingCriterion.min_mandatory_gap),
                RankingPreference(RankingCriterion.average_all_gap),
                RankingPreference(RankingCriterion.elective_collision_count),
                RankingPreference(RankingCriterion.mandatory_span),
                RankingPreference(RankingCriterion.max_exams_per_day),
            ]
        )

        first_service = FakeProgressiveRankingService()
        first_update = presenter.rank_progressively(
            settings,
            run_id=1,
            ranking_service=first_service,
            batch_size=17,
            preview_limit=50,
            min_update_interval_seconds=0,
        )
        presenter.update_schedules(
            first_update.ranked_schedules,
            is_partial=False,
            systems_seen=first_update.total_count,
            displayed_count=first_update.displayed_count,
        )

        second_service = FakeProgressiveRankingService()
        second_update = presenter.rank_progressively(
            settings,
            run_id=2,
            ranking_service=second_service,
            batch_size=19,
            preview_limit=50,
            min_update_interval_seconds=0,
        )

        self.assertEqual(first_service.sources, systems)
        self.assertEqual(second_service.sources, systems)
        self.assertEqual(first_update.total_count, 60)
        self.assertEqual(second_update.total_count, 60)
        self.assertEqual(len(second_update.ranked_schedules), 60)
        self.assertIs(second_update.ranked_schedules[0].exam_system, systems[59])
        self.assertEqual(len(cache.get_generated_schedules()), 60)
        self.assertEqual(len(cache.ranked_schedules), 60)

    @staticmethod
    def _numbered_systems(count: int) -> list[ExamSystem]:
        return [
            make_system(
                exams=[
                    make_exam(
                        f"Course {index}",
                        f"83{index:03d}",
                        date(2026, 1, 1),
                    )
                ]
            )
            for index in range(count)
        ]


class ScheduleNavigationPresenterPart4Tests(unittest.TestCase):
    """Part 4 GUI-facing behavior without opening a desktop window."""

    def _max_per_day_settings(self, value: int):
        settings = SchedulingConstraintSettings.default_configuration()
        settings.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(True, value)
        )
        return settings

    def _fall_period(self):
        return ExamPeriod(
            semester="FALL",
            moed="Aleph",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
            excluded_dates=[],
        )

    def test_current_view_marks_overloaded_days(self) -> None:
        """A day above max_exams_per_day is visible to the GUI."""
        system = make_system(
            exams=[
                make_exam("A", "83001", date(2026, 1, 1), status="Elective"),
                make_exam("B", "83002", date(2026, 1, 1), status="Elective"),
            ]
        )
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(settings=self._max_per_day_settings(1)),
        )

        status = presenter.current_view().day_status_by_iso_date["2026-01-01"]

        self.assertEqual(status.status, "overloaded")
        self.assertIn("maximum allowed is 1", status.details)

    def test_current_view_marks_conflict_days_stronger_than_busy_days(self) -> None:
        """Mandatory same-day conflicts are marked as conflict."""
        system = make_system(
            exams=[
                make_exam("A", "83001", date(2026, 1, 1)),
                make_exam("B", "83002", date(2026, 1, 1)),
            ]
        )
        presenter = ScheduleNavigationPresenter([system])

        status = presenter.current_view().day_status_by_iso_date["2026-01-01"]

        self.assertEqual(status.status, "conflict")
        self.assertIn("Courses 83001 and 83002 conflict", status.details)

    def test_snapshot_save_load_and_compare_use_active_schedule(self) -> None:
        """Snapshots can be saved, compared, and loaded without regeneration."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(periods=[self._fall_period()]),
        )

        self.assertTrue(presenter.save_snapshot("base").success)

        course = presenter.manual_move_course_options()[0]
        move = presenter.apply_manual_move(course, "02-01-2026")
        self.assertTrue(move.success)
        self.assertTrue(presenter.save_snapshot("moved").success)

        comparison = presenter.compare_snapshots("base", "moved")
        self.assertTrue(comparison.success)
        self.assertIn("83001 - Algorithms", comparison.details)
        self.assertIn("01-01-2026 -> 02-01-2026", comparison.details)

        load = presenter.load_snapshot("base")
        self.assertTrue(load.success)
        self.assertIn("2026-01-01", presenter.current_view().exams_by_iso_date)

    def test_snapshot_save_stores_ranked_penalty_score(self) -> None:
        """Fallback-ranked schedules persist their real penalty score."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        ranked = make_ranked(
            system,
            key=1,
            penalty_score=50.0,
            penalty_details=("REQ-2: gap violation (penalty 50)",),
            is_fallback=True,
        )
        presenter = ScheduleNavigationPresenter([ranked])

        view = presenter.current_view()
        self.assertTrue(view.is_fallback)
        self.assertEqual(view.penalty_score, 50.0)
        self.assertTrue(presenter.save_snapshot("fallback").success)

        snapshot = presenter._snapshot_by_name("fallback")
        self.assertEqual(snapshot.penalty_score, 50.0)

    def test_snapshot_summaries_use_friendly_quality_labels(self) -> None:
        """Snapshot list labels should not expose raw enum names."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter([system])
        presenter._snapshot_manager.save(
            "review",
            system,
            quality_tag=ScheduleQualityTag.NEEDS_REVIEW,
        )

        summaries = presenter.snapshot_summaries()

        self.assertEqual(summaries[0].quality_tag, "Needs Review")
        self.assertNotIn("ScheduleQualityTag", summaries[0].quality_tag)

    def test_compare_snapshots_reports_penalty_delta_without_date_changes(self) -> None:
        """Score-only differences should still appear in comparison output."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter(
            [make_ranked(system, key=1, penalty_score=50.0)]
        )

        self.assertTrue(presenter.save_snapshot("first").success)
        presenter.apply_ranked_schedules(
            [make_ranked(system, key=1, penalty_score=10.0)]
        )
        self.assertTrue(presenter.save_snapshot("second").success)

        comparison = presenter.compare_snapshots("first", "second")
        self.assertTrue(comparison.success)
        self.assertIn("Penalty score (lower is better)", comparison.details)
        self.assertIn("50 -> 10", comparison.details)
        self.assertIn("-40", comparison.details)
        self.assertIn("No changed courses.", comparison.details)
        self.assertIsNotNone(comparison.comparison)
        self.assertEqual(comparison.comparison.first_penalty, "50")
        self.assertEqual(comparison.comparison.second_penalty, "10")
        self.assertEqual(
            comparison.comparison.penalty_delta_label,
            "Constraint penalty: 50 \u2192 10 \u2014 improved",
        )
        self.assertEqual(
            comparison.comparison.quality_change_label,
            "Quality change: Risky \u2192 Risky \u2014 unchanged",
        )
        self.assertEqual(
            comparison.comparison.empty_message,
            "No exam date changes between these snapshots.",
        )

    def test_compare_snapshots_builds_structured_display_model(self) -> None:
        """Presenter exposes GUI-ready comparison sections and changed rows."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(periods=[self._fall_period()]),
        )
        presenter._snapshot_manager.save(
            "original",
            system,
            quality_tag=ScheduleQualityTag.RISKY,
            penalty_score=4,
        )

        course = presenter.manual_move_course_options()[0]
        self.assertTrue(presenter.apply_manual_move(course, "02-01-2026").success)
        presenter._snapshot_manager.save(
            "after-change",
            presenter.current_system(),
            quality_tag=ScheduleQualityTag.NEEDS_REVIEW,
            penalty_score=2,
        )

        result = presenter.compare_snapshots("original", "after-change")

        self.assertTrue(result.success)
        view = result.comparison
        self.assertIsNotNone(view)
        self.assertEqual(view.header, "Comparison: original \u2192 after-change")
        self.assertEqual(view.first_quality, "Risky")
        self.assertEqual(view.second_quality, "Needs Review")
        self.assertEqual(view.first_penalty, "4")
        self.assertEqual(view.second_penalty, "2")
        self.assertEqual(
            view.quality_change_label,
            "Quality change: Risky \u2192 Needs Review \u2014 improved",
        )
        self.assertEqual(
            view.penalty_delta_label,
            "Constraint penalty: 4 \u2192 2 \u2014 improved",
        )
        self.assertEqual(len(view.changed_rows), 1)
        row = view.changed_rows[0]
        self.assertEqual(row.change_label, "Moved exam")
        self.assertEqual(row.course_label, "83001 - Algorithms")
        self.assertEqual(row.period_label, "FALL Aleph")
        self.assertEqual(row.old_date, "01-01-2026")
        self.assertEqual(row.new_date, "02-01-2026")

    def test_manual_move_undo_and_redo_update_visible_schedule(self) -> None:
        """Undo and redo change only the active visible schedule."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(periods=[self._fall_period()]),
        )

        course = presenter.manual_move_course_options()[0]
        result = presenter.apply_manual_move(course, "02-01-2026")

        self.assertTrue(result.success)
        self.assertTrue(presenter.can_undo_manual_move)
        self.assertIn("2026-01-02", presenter.current_view().exams_by_iso_date)

        undo = presenter.undo_manual_move()
        self.assertTrue(undo.success)
        self.assertTrue(presenter.can_redo_manual_move)
        self.assertIn("2026-01-01", presenter.current_view().exams_by_iso_date)

        redo = presenter.redo_manual_move()
        self.assertTrue(redo.success)
        self.assertIn("2026-01-02", presenter.current_view().exams_by_iso_date)

    def test_manual_move_selector_distinguishes_aleph_and_bet_for_one_course(self) -> None:
        """The GUI label must identify the exact exam the user selected."""
        system = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    "FALL",
                    "Aleph",
                    [make_exam("Algorithms", "83001", date(2026, 1, 1))],
                ),
                ExamSchedule(
                    "FALL",
                    "Bet",
                    [make_exam("Algorithms", "83001", date(2026, 2, 1))],
                ),
            ]
        )
        periods = [
            ExamPeriod("FALL", "Aleph", date(2026, 1, 1), date(2026, 1, 2), []),
            ExamPeriod("FALL", "Bet", date(2026, 2, 1), date(2026, 2, 2), []),
        ]
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(periods=periods),
        )

        options = presenter.manual_move_course_options()
        bet_option = next(option for option in options if "FALL Bet" in option)

        result = presenter.apply_manual_move(bet_option, "02-02-2026")

        self.assertTrue(result.success)
        moved = presenter.current_system()
        dates = {
            (location.semester, location.moed): location.exam_date
            for location in flatten_exam_system(moved)
        }
        self.assertEqual(dates[("FALL", "Aleph")], date(2026, 1, 1))
        self.assertEqual(dates[("FALL", "Bet")], date(2026, 2, 2))

    def test_manual_move_dates_exclude_the_current_exam_date(self) -> None:
        """The move menu offers only dates that would actually change the exam."""
        system = make_system(
            exams=[make_exam("Algorithms", "83001", date(2026, 1, 1))]
        )
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(periods=[self._fall_period()]),
        )
        presenter._manual_editor._impact_service.analyze = MagicMock(
            side_effect=AssertionError("The date picker must not calculate impact.")
        )

        dates = presenter.manual_move_date_options(
            presenter.manual_move_course_options()[0]
        )

        self.assertNotIn("01-01-2026", dates)
        self.assertIn("02-01-2026", dates)
        presenter._manual_editor._impact_service.analyze.assert_not_called()

    def test_manual_move_dates_hide_critical_conflicts(self) -> None:
        """The picker must not offer a date that collides with a mandatory exam."""
        system = make_system(
            exams=[
                make_exam("Algorithms", "83001", date(2026, 1, 1)),
                make_exam("Physics", "83002", date(2026, 1, 2)),
            ]
        )
        presenter = ScheduleNavigationPresenter(
            [system],
            cache_manager=FakeCache(periods=[self._fall_period()]),
        )
        presenter._manual_editor._impact_service.analyze = MagicMock(
            side_effect=AssertionError("The date picker must not calculate impact.")
        )

        dates = presenter.manual_move_date_options(
            presenter.manual_move_course_options()[0]
        )

        self.assertNotIn("01-01-2026", dates)
        self.assertNotIn("02-01-2026", dates)
        self.assertIn("03-01-2026", dates)
        presenter._manual_editor._impact_service.analyze.assert_not_called()
