"""Unit tests for ScheduleNavigationPresenter (SCRUM-126).

These tests verify navigation state (next/previous/counter) and the
display-ready view built from generated exam systems, without any GUI.
"""
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

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
    )


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

    def test_apply_ranking_reorders_existing_ranked_systems_without_generation(self) -> None:
        """Ranking controls should use existing metrics, not regenerate schedules."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        first_ranked = make_ranked(first, key=1, min_gap=2)
        second_ranked = make_ranked(second, key=2, min_gap=9)

        class FakeRankingService:
            def __init__(self):
                self.rank_generated_schedules_called = False

            def rank_generated_schedules(self, *_args):
                self.rank_generated_schedules_called = True
                raise AssertionError("generation-order metrics should not recalculate")

            def rerank(self, ranked_schedules, ranking_settings):
                from scheduling.scheduleRankingService import ScheduleRankingOutcome
                from scheduling.scheduleRanker import ScheduleRanker

                return ScheduleRankingOutcome(
                    ranked_schedules=ScheduleRanker().rank(
                        ranked_schedules,
                        ranking_settings,
                    ),
                    elapsed_seconds=0.25,
                )

        service = FakeRankingService()
        presenter = ScheduleNavigationPresenter([first_ranked, second_ranked])

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
        self.assertFalse(service.rank_generated_schedules_called)
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

    def test_apply_empty_ranking_restores_generation_order_by_key(self) -> None:
        """Removing all criteria restores the original generated order."""
        first = make_system(exams=[make_exam("First", "83001", date(2026, 1, 1))])
        second = make_system(exams=[make_exam("Second", "83002", date(2026, 1, 2))])
        first_ranked = make_ranked(first, key=1)
        second_ranked = make_ranked(second, key=2)
        presenter = ScheduleNavigationPresenter([second_ranked, first_ranked])

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
        presenter = ScheduleNavigationPresenter(
            [
                make_ranked(
                    first,
                    key=1,
                    min_gap=10,
                    average_gap=3.0,
                    elective_collisions=0,
                    mandatory_span=8,
                    max_exams_per_day=1,
                ),
                make_ranked(
                    second,
                    key=2,
                    min_gap=4,
                    average_gap=9.0,
                    elective_collisions=2,
                    mandatory_span=12,
                    max_exams_per_day=3,
                ),
            ]
        )

        presenter.apply_ranking(
            RankingSettings(
                [RankingPreference(RankingCriterion.min_mandatory_gap)]
            )
        )
        first_metrics = presenter.current_view().metrics_summary
        self.assertEqual(first_metrics.schedule_id, 1)
        self.assertEqual(first_metrics.min_mandatory_gap, 10)

        presenter.apply_ranking(
            RankingSettings(
                [RankingPreference(RankingCriterion.average_all_gap)]
            )
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

    def test_progressive_ranking_emits_partial_top_preview_and_final_top_only(self) -> None:
        """Progressive Apply Ranking keeps navigation bounded to computed preview."""
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
        self.assertEqual(final.displayed_count, 3)
        self.assertIn("Final Top 3", final.message)

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

    def test_live_update_resets_to_first_when_current_ranked_identity_disappears(self) -> None:
        """If a browsed preview item drops out of Top 50, reset safely."""
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

        self.assertIs(presenter.current_system(), third)
        self.assertEqual(presenter.position(), 1)

if __name__ == "__main__":
    unittest.main()


class _RecordingRankingCache:
    def __init__(self) -> None:
        self.ranking_settings = None
        self.ranked_schedules = None
        self.set_ranked_calls = 0

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
        cache = _RecordingRankingCache()
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
        cache = _RecordingRankingCache()
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
