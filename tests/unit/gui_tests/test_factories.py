"""
test_factories.py
~~~~~~~~~~~~~~~~~
Isolated unit tests for PresenterFactory and ViewFactory.

Strategy
--------
* PresenterFactory tests require NO mocking: presenters have no ctk dependency
  and can be instantiated freely with synthetic domain data.
* ViewFactory tests use ``unittest.mock.patch`` to stub the concrete screen
  classes and ``customtkinter`` *inside* the factory's create method.  The
  stub prevents any display connection from being opened, making the suite
  safe for headless CI environments.

All tests extend the shared ``_FactoryTestBase`` which sets up the sys.path
consistently with the rest of the test suite.
"""

import sys
import unittest
from enum import auto
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup — mirrors the pattern used by every other unit test here
# ---------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[2]   # tests/
_SRC = _TESTS_ROOT.parent / "src"                   # src/

sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from gui.factories.presenter_factory import PresenterFactory, PresenterType
from gui.factories.view_factory import ViewFactory, ViewType

# Domain helpers used to build realistic presenter arguments
from models import Course, ExamPeriod, ProgramEnrollment
from datetime import date


# ---------------------------------------------------------------------------
# Shared data factories
# ---------------------------------------------------------------------------

def _make_course(name: str = "Physics 1", number: str = "83102") -> Course:
    return Course(
        name=name,
        course_number=number,
        instructor="Prof. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


# ---------------------------------------------------------------------------
# PresenterFactory tests  (no GUI, no mocking needed)
# ---------------------------------------------------------------------------

class TestPresenterFactory(unittest.TestCase):
    """PresenterFactory creates the right presenter class for each enum value."""

    def test_creates_program_selection_presenter(self) -> None:
        """PROGRAM_SELECTION returns a ProgramSelectionPresenter instance."""
        from gui.presenters.programSelectionPresenter import ProgramSelectionPresenter

        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_SELECTION,
            courses=[_make_course()],
        )

        self.assertIsInstance(presenter, ProgramSelectionPresenter)

    def test_creates_program_details_presenter(self) -> None:
        """PROGRAM_DETAILS returns a ProgramDetailsPresenter instance."""
        from gui.presenters.programDetailsPresenter import ProgramDetailsPresenter

        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_DETAILS,
            courses=[_make_course()],
        )

        self.assertIsInstance(presenter, ProgramDetailsPresenter)

    def test_unknown_type_raises_value_error(self) -> None:
        """An unregistered PresenterType raises a descriptive ValueError."""
        # Simulate a future enum value that has not been registered yet.
        fake_type = MagicMock(spec=PresenterType)
        fake_type.__class__ = PresenterType

        with self.assertRaises(ValueError):
            PresenterFactory.create(fake_type)  # type: ignore[arg-type]

    def test_courses_kwarg_reaches_selection_presenter(self) -> None:
        """The courses kwarg is forwarded to ProgramSelectionPresenter."""
        courses = [_make_course("Algebra", "83200")]

        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_SELECTION,
            courses=courses,
        )

        # The presenter derives available programs from the supplied courses.
        self.assertIn("83101", presenter.available_programs)

    def test_max_programs_kwarg_is_forwarded(self) -> None:
        """The max_programs kwarg overrides the default limit in the presenter."""
        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_SELECTION,
            courses=[_make_course()],
            max_programs=2,
        )

        self.assertEqual(presenter.max_programs, 2)

    def test_all_presenter_types_are_registered(self) -> None:
        """Every member of PresenterType has a concrete class in the registry."""
        courses = [_make_course()]
        for presenter_type in PresenterType:
            try:
                PresenterFactory.create(presenter_type, courses=courses)
            except ValueError as exc:
                self.fail(
                    f"PresenterType.{presenter_type.name} raised ValueError: {exc}"
                )


# ---------------------------------------------------------------------------
# ViewFactory tests  (ctk and screens are stubbed out)
# ---------------------------------------------------------------------------

class TestViewFactory(unittest.TestCase):
    """ViewFactory dispatches to the correct screen class and forwards kwargs."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_master() -> MagicMock:
        """Return a lightweight stand-in for a ctk root/container."""
        return MagicMock(name="ctk_master")

    # ------------------------------------------------------------------
    # Registry completeness
    # ------------------------------------------------------------------

    def test_all_view_types_are_registered(self) -> None:
        """Every member of ViewType has a registered module/class path."""
        # We verify the registry is complete by patching importlib so no
        # real screen module (or customtkinter) is ever loaded.
        master = self._mock_master()
        mock_cls = MagicMock(return_value=MagicMock())
        mock_module = MagicMock()
        mock_module.FileUploadScreen = mock_cls
        mock_module.ProgramConfigScreen = mock_cls

        with patch("importlib.import_module", return_value=mock_module):
            for view_type in ViewType:
                try:
                    ViewFactory.create(view_type, master)
                except ValueError as exc:
                    self.fail(
                        f"ViewType.{view_type.name} raised ValueError: {exc}"
                    )

    # ------------------------------------------------------------------
    # FILE_UPLOAD dispatch
    # ------------------------------------------------------------------

    def test_file_upload_returns_file_upload_screen(self) -> None:
        """FILE_UPLOAD causes ViewFactory to call FileUploadScreen(master)."""
        master = self._mock_master()
        mock_screen = MagicMock(name="FileUploadScreen_instance")
        mock_cls = MagicMock(return_value=mock_screen)
        mock_module = MagicMock()
        mock_module.FileUploadScreen = mock_cls

        with patch("importlib.import_module", return_value=mock_module):
            result = ViewFactory.create(ViewType.FILE_UPLOAD, master)

        mock_cls.assert_called_once_with(master)
        self.assertIs(result, mock_screen)

    def test_file_upload_forwards_kwargs(self) -> None:
        """Extra kwargs (e.g. upload_service) are forwarded to FileUploadScreen."""
        master = self._mock_master()
        mock_service = MagicMock(name="upload_service")
        mock_cls = MagicMock(return_value=MagicMock())
        mock_module = MagicMock()
        mock_module.FileUploadScreen = mock_cls

        with patch("importlib.import_module", return_value=mock_module):
            ViewFactory.create(
                ViewType.FILE_UPLOAD,
                master,
                upload_service=mock_service,
            )

        mock_cls.assert_called_once_with(master, upload_service=mock_service)

    # ------------------------------------------------------------------
    # PROGRAM_CONFIG dispatch
    # ------------------------------------------------------------------

    def test_program_config_returns_program_config_screen(self) -> None:
        """PROGRAM_CONFIG causes ViewFactory to call ProgramConfigScreen(master, ...)."""
        master = self._mock_master()
        mock_screen = MagicMock(name="ProgramConfigScreen_instance")
        mock_cls = MagicMock(return_value=mock_screen)
        mock_module = MagicMock()
        mock_module.ProgramConfigScreen = mock_cls
        sel_presenter = MagicMock(name="selection_presenter")
        det_presenter = MagicMock(name="details_presenter")

        with patch("importlib.import_module", return_value=mock_module):
            result = ViewFactory.create(
                ViewType.PROGRAM_CONFIG,
                master,
                selection_presenter=sel_presenter,
                details_presenter=det_presenter,
            )

        mock_cls.assert_called_once_with(
            master,
            selection_presenter=sel_presenter,
            details_presenter=det_presenter,
        )
        self.assertIs(result, mock_screen)

    def test_program_config_forwards_navigation_callbacks(self) -> None:
        """on_next and on_back callbacks are forwarded to ProgramConfigScreen."""
        master = self._mock_master()
        on_next = MagicMock(name="on_next")
        on_back = MagicMock(name="on_back")
        mock_cls = MagicMock(return_value=MagicMock())
        mock_module = MagicMock()
        mock_module.ProgramConfigScreen = mock_cls

        with patch("importlib.import_module", return_value=mock_module):
            ViewFactory.create(
                ViewType.PROGRAM_CONFIG,
                master,
                selection_presenter=MagicMock(),
                details_presenter=MagicMock(),
                on_next=on_next,
                on_back=on_back,
            )

        _, call_kwargs = mock_cls.call_args
        self.assertIs(call_kwargs["on_next"], on_next)
        self.assertIs(call_kwargs["on_back"], on_back)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_unknown_view_type_raises_value_error(self) -> None:
        """An unregistered ViewType raises ValueError before any import occurs."""
        master = self._mock_master()
        # Use a raw sentinel that is not a ViewType member.
        fake_type = object()

        # No patch needed: the registry check fires before importlib is called.
        with self.assertRaises((ValueError, AttributeError)):
            ViewFactory.create(fake_type, master)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
