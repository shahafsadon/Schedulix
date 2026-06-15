"""
test_factories.py
~~~~~~~~~~~~~~~~~
Isolated unit tests for PresenterFactory and ViewFactory.

Strategy
--------
* PresenterFactory tests require NO mocking: presenters have no ctk dependency
  and can be instantiated freely with synthetic domain data.
* ViewFactory tests use ``unittest.mock.patch`` to stub the concrete screen
  classes inside the factory's create method. The stub prevents any display
  connection from being opened, making the suite safe for headless CI
  environments.

All tests extend unittest.TestCase and set up sys.path consistently with the
rest of the test suite.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup — mirrors the pattern used by every other unit test here
# ---------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[2]  # tests/
_SRC = _TESTS_ROOT.parent / "src"  # src/

sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from gui.factories.presenter_factory import PresenterFactory, PresenterType
from gui.factories.view_factory import ViewFactory, ViewType

# Domain helpers used to build realistic presenter arguments
from models import Course, ProgramEnrollment


# ---------------------------------------------------------------------------
# Shared data factories
# ---------------------------------------------------------------------------

def _make_course(
    name: str = "Physics 1",
    number: str = "83102",
) -> Course:
    return Course(
        name=name,
        course_number=number,
        instructor="Prof. Test",
        programs=[
            ProgramEnrollment(
                "83101",
                1,
                "FALL",
                "Obligatory",
            )
        ],
        evaluation_type="Exam",
    )


# ---------------------------------------------------------------------------
# PresenterFactory tests — no GUI and no mocking needed
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

        self.assertIsInstance(
            presenter,
            ProgramSelectionPresenter,
        )

    def test_creates_program_details_presenter(self) -> None:
        """PROGRAM_DETAILS returns a ProgramDetailsPresenter instance."""
        from gui.presenters.programDetailsPresenter import ProgramDetailsPresenter

        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_DETAILS,
            courses=[_make_course()],
        )

        self.assertIsInstance(
            presenter,
            ProgramDetailsPresenter,
        )

    def test_unknown_type_raises_value_error(self) -> None:
        """An unregistered PresenterType raises a descriptive ValueError."""
        fake_type = MagicMock(spec=PresenterType)
        fake_type.__class__ = PresenterType

        with self.assertRaises(ValueError):
            PresenterFactory.create(
                fake_type,  # type: ignore[arg-type]
            )

    def test_courses_kwarg_reaches_selection_presenter(self) -> None:
        """The courses kwarg is forwarded to ProgramSelectionPresenter."""
        courses = [
            _make_course(
                "Algebra",
                "83200",
            )
        ]

        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_SELECTION,
            courses=courses,
        )

        self.assertIn(
            "83101",
            presenter.available_programs,
        )

    def test_max_programs_kwarg_is_forwarded(self) -> None:
        """The max_programs kwarg overrides the presenter's default limit."""
        presenter = PresenterFactory.create(
            PresenterType.PROGRAM_SELECTION,
            courses=[_make_course()],
            max_programs=2,
        )

        self.assertEqual(
            presenter.max_programs,
            2,
        )

    def test_all_presenter_types_are_registered(self) -> None:
        """Every PresenterType member has a concrete class in the registry."""
        courses = [_make_course()]
        from constraint_settings import SchedulingConstraintSettings

        cache = MagicMock()
        cache.get_constraint_settings.return_value = (
            SchedulingConstraintSettings.default_configuration()
        )

        kwargs_by_type = {
            PresenterType.PROGRAM_SELECTION: {"courses": courses},
            PresenterType.PROGRAM_DETAILS: {"courses": courses},
            PresenterType.SCHEDULING_SETTINGS: {"cache_manager": cache},
        }

        for presenter_type, kwargs in kwargs_by_type.items():
            try:
                PresenterFactory.create(presenter_type, **kwargs)
            except ValueError as exc:
                self.fail(
                    f"PresenterType.{presenter_type.name} "
                    f"raised ValueError: {exc}"
                )


# ---------------------------------------------------------------------------
# ViewFactory tests — concrete screens are stubbed out
# ---------------------------------------------------------------------------

class TestViewFactory(unittest.TestCase):
    """ViewFactory dispatches to the correct screen class and forwards kwargs."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_master() -> MagicMock:
        """Return a lightweight stand-in for a ctk root or container."""
        return MagicMock(
            name="ctk_master",
        )

    # ------------------------------------------------------------------
    # Registry completeness
    # ------------------------------------------------------------------

    def test_all_view_types_are_registered(self) -> None:
        """Every ViewType resolves its exact module and concrete class name.

        A plain object is used instead of MagicMock for the imported module.
        MagicMock fabricates missing attributes dynamically and can make an
        incomplete registry test pass when a concrete class is absent.
        """
        master = self._mock_master()

        cases = {
            ViewType.FILE_UPLOAD: (
                "gui.fileUploadScreen",
                "FileUploadScreen",
            ),
            ViewType.PROGRAM_CONFIG: (
                "gui.programConfigScreen",
                "ProgramConfigScreen",
            ),
            ViewType.DATE_MANAGEMENT: (
                "gui.dateManagementScreen",
                "DateManagementScreen",
            ),
            ViewType.SCHEDULE_NAVIGATION: (
                "gui.scheduleNavigationScreen",
                "ScheduleNavigationScreen",
            ),
        }

        for view_type, (
            expected_module,
            expected_class,
        ) in cases.items():
            with self.subTest(view_type=view_type):
                mock_screen = MagicMock(
                    name=f"{expected_class}_instance",
                )

                mock_cls = MagicMock(
                    return_value=mock_screen,
                )

                imported_module = SimpleNamespace(
                    **{
                        expected_class: mock_cls,
                    }
                )

                with patch(
                    "importlib.import_module",
                    return_value=imported_module,
                ) as importer:
                    result = ViewFactory.create(
                        view_type,
                        master,
                        marker=view_type.name,
                    )

                importer.assert_called_once_with(
                    expected_module,
                )

                mock_cls.assert_called_once_with(
                    master,
                    marker=view_type.name,
                )

                self.assertIs(
                    result,
                    mock_screen,
                )

    # ------------------------------------------------------------------
    # FILE_UPLOAD dispatch
    # ------------------------------------------------------------------

    def test_file_upload_returns_file_upload_screen(self) -> None:
        """FILE_UPLOAD causes ViewFactory to call FileUploadScreen(master)."""
        master = self._mock_master()

        mock_screen = MagicMock(
            name="FileUploadScreen_instance",
        )

        mock_cls = MagicMock(
            return_value=mock_screen,
        )

        mock_module = SimpleNamespace(
            FileUploadScreen=mock_cls,
        )

        with patch(
            "importlib.import_module",
            return_value=mock_module,
        ):
            result = ViewFactory.create(
                ViewType.FILE_UPLOAD,
                master,
            )

        mock_cls.assert_called_once_with(
            master,
        )

        self.assertIs(
            result,
            mock_screen,
        )

    def test_file_upload_forwards_kwargs(self) -> None:
        """Extra kwargs are forwarded to FileUploadScreen."""
        master = self._mock_master()

        mock_service = MagicMock(
            name="upload_service",
        )

        mock_cls = MagicMock(
            return_value=MagicMock(),
        )

        mock_module = SimpleNamespace(
            FileUploadScreen=mock_cls,
        )

        with patch(
            "importlib.import_module",
            return_value=mock_module,
        ):
            ViewFactory.create(
                ViewType.FILE_UPLOAD,
                master,
                upload_service=mock_service,
            )

        mock_cls.assert_called_once_with(
            master,
            upload_service=mock_service,
        )

    # ------------------------------------------------------------------
    # PROGRAM_CONFIG dispatch
    # ------------------------------------------------------------------

    def test_program_config_returns_program_config_screen(self) -> None:
        """PROGRAM_CONFIG constructs ProgramConfigScreen with its presenters."""
        master = self._mock_master()

        mock_screen = MagicMock(
            name="ProgramConfigScreen_instance",
        )

        mock_cls = MagicMock(
            return_value=mock_screen,
        )

        mock_module = SimpleNamespace(
            ProgramConfigScreen=mock_cls,
        )

        selection_presenter = MagicMock(
            name="selection_presenter",
        )

        details_presenter = MagicMock(
            name="details_presenter",
        )

        with patch(
            "importlib.import_module",
            return_value=mock_module,
        ):
            result = ViewFactory.create(
                ViewType.PROGRAM_CONFIG,
                master,
                selection_presenter=selection_presenter,
                details_presenter=details_presenter,
            )

        mock_cls.assert_called_once_with(
            master,
            selection_presenter=selection_presenter,
            details_presenter=details_presenter,
        )

        self.assertIs(
            result,
            mock_screen,
        )

    def test_program_config_forwards_navigation_callbacks(self) -> None:
        """on_next and on_back callbacks are forwarded to ProgramConfigScreen."""
        master = self._mock_master()

        on_next = MagicMock(
            name="on_next",
        )

        on_back = MagicMock(
            name="on_back",
        )

        mock_cls = MagicMock(
            return_value=MagicMock(),
        )

        mock_module = SimpleNamespace(
            ProgramConfigScreen=mock_cls,
        )

        with patch(
            "importlib.import_module",
            return_value=mock_module,
        ):
            ViewFactory.create(
                ViewType.PROGRAM_CONFIG,
                master,
                selection_presenter=MagicMock(),
                details_presenter=MagicMock(),
                on_next=on_next,
                on_back=on_back,
            )

        _, call_kwargs = mock_cls.call_args

        self.assertIs(
            call_kwargs["on_next"],
            on_next,
        )

        self.assertIs(
            call_kwargs["on_back"],
            on_back,
        )

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_unknown_view_type_raises_value_error(self) -> None:
        """An unregistered ViewType raises ValueError before importing a screen."""
        master = self._mock_master()
        fake_type = object()

        with self.assertRaises(ValueError):
            ViewFactory.create(
                fake_type,  # type: ignore[arg-type]
                master,
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
