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
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem
from gui.scheduleNavigationPresenter import ScheduleNavigationPresenter


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

if __name__ == "__main__":
    unittest.main()