"""Unit tests for ExportPresenter (SCRUM-127).

These tests verify that the presenter reads the currently displayed system from
the navigation presenter, hands it to the export service, and turns the
outcome into a display-ready result — without a GUI. Cancellation and missing
schedules are also covered.
"""
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from models import Course, ProgramEnrollment
from gui.presenters.exportPresenter import ExportPresenter
from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter
from output.exportService import ExportOutcome
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


def make_system(name="Physics 1", course_number="83102") -> ExamSystem:
    """Build a one-exam ExamSystem for presenter tests."""
    course = Course(
        name=name,
        course_number=course_number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )
    return ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=[ScheduledExam(course=course, exam_date=date(2026, 1, 29))],
            )
        ]
    )


class _FakeService:
    """Captures the system it was asked to export and returns a scripted outcome."""

    def __init__(self, outcome: ExportOutcome) -> None:
        """Store the outcome and prepare a capture slot for the call."""
        self._outcome = outcome
        # Recorded so tests can assert which system reached the service.
        self.exported_system = None
        self.exported_path = None

    def export(self, system, output_path):
        """Mimic ExportService.export by capturing args and returning the outcome."""
        self.exported_system = system
        self.exported_path = output_path
        return self._outcome


class ExportPresenterTests(unittest.TestCase):
    """Presenter translation of export outcomes into user-facing results."""

    def test_exports_currently_displayed_system(self) -> None:
        """The system at the navigation presenter's current index is exported."""
        first = make_system("First", "83102")
        second = make_system("Second", "83103")
        navigation = ScheduleNavigationPresenter([first, second])
        navigation.next()   # move to the second system

        service = _FakeService(
            ExportOutcome(success=True, path=Path("/tmp/out.txt"))
        )
        presenter = ExportPresenter(navigation, service)

        result = presenter.export_current(Path("/tmp/out.txt"))

        # The service must receive the currently shown system, not the first one.
        self.assertIs(service.exported_system, second)
        self.assertTrue(result.success)
        self.assertEqual(result.path, Path("/tmp/out.txt"))

    def test_cancelled_dialog_is_not_an_error(self) -> None:
        """A None path (user cancelled) returns a non-success result quietly."""
        navigation = ScheduleNavigationPresenter([make_system()])
        service = _FakeService(ExportOutcome(success=True, path=Path("/tmp/x")))
        presenter = ExportPresenter(navigation, service)

        result = presenter.export_current(None)

        self.assertFalse(result.success)
        self.assertIn("cancelled", result.message.lower())
        # The service must NOT be called when the user cancels.
        self.assertIsNone(service.exported_system)

    def test_no_schedule_yields_friendly_failure(self) -> None:
        """Trying to export with no generated schedules is a clean failure."""
        navigation = ScheduleNavigationPresenter([])
        presenter = ExportPresenter(navigation, _FakeService(
            ExportOutcome(success=True, path=Path("/tmp/x"))
        ))

        result = presenter.export_current(Path("/tmp/x.txt"))

        self.assertFalse(result.success)
        self.assertIn("No schedule", result.message)

    def test_service_failure_propagates_as_user_message(self) -> None:
        """A failed service outcome becomes a failure result with its message."""
        navigation = ScheduleNavigationPresenter([make_system()])
        service = _FakeService(
            ExportOutcome(success=False, error_message="permission denied")
        )
        presenter = ExportPresenter(navigation, service)

        result = presenter.export_current(Path("/tmp/x.txt"))

        self.assertFalse(result.success)
        self.assertIn("permission denied", result.message)

    def test_partial_live_preview_cannot_be_exported_as_final_ranked_result(self) -> None:
        """Temporary Top 50 previews are not final exportable ranking output."""
        navigation = ScheduleNavigationPresenter([make_system()])
        navigation.update_schedules(
            [make_system()],
            is_partial=True,
            systems_seen=10,
            displayed_count=1,
        )
        service = _FakeService(ExportOutcome(success=True, path=Path("/tmp/x")))
        presenter = ExportPresenter(navigation, service)

        result = presenter.export_current(Path("/tmp/x.txt"))

        self.assertFalse(result.success)
        self.assertIn("Temporary ranking previews", result.message)
        self.assertIsNone(service.exported_system)


if __name__ == "__main__":
    unittest.main()
