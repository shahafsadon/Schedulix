"""Presenter for exporting the currently navigated exam system (SCRUM-127).

This presenter sits between the "Save Final System" action on the navigation
screen and the ExportService. Following the MVP pattern it imports no GUI code: the
View asks for the path via a "Save As..." dialog (a customtkinter concern), then
hands the chosen path here. The presenter reads the currently displayed system
from the navigation presenter (single source of truth), runs the export, and
returns a display-ready result.

Keeping the dialog out of the presenter is what makes the presenter testable
without a display.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter
from output.exportService import ExportService


@dataclass(frozen=True)
class ExportResult:
    """Display-ready outcome of an export action.

    The View shows `message` directly; on success `path` is the file the user
    can open. On failure `success` is False and `message` is a friendly reason.
    """

    success: bool
    message: str
    path: Path | None = None


class ExportPresenter:
    """Drives the export action triggered from the navigation screen."""

    def __init__(
        self,
        navigation_presenter: ScheduleNavigationPresenter,
        service: ExportService | None = None,
    ) -> None:
        """Create the presenter.

        Args:
            navigation_presenter: the presenter that knows which exam system
                is currently shown on screen and is therefore the one to export.
            service: the export service; a default is created when none is
                supplied, while tests can inject a fake.
        """
        self._navigation = navigation_presenter
        # Default to the real service so application code stays simple.
        self._service = service or ExportService()

    def export_current(self, output_path: str | Path | None) -> ExportResult:
        """Export the system currently shown by the navigation presenter.

        Args:
            output_path: the file path chosen by the user via the Save As
                dialog. None means the user cancelled the dialog, which is not
                an error but should not write anything.
        """
        # User cancelled the Save As dialog: explicitly NOT an error.
        if output_path is None:
            return ExportResult(
                success=False,
                message="Export cancelled.",
            )

        # Nothing to export if no system is currently displayed (defensive:
        # the Save button should be disabled in that state anyway).
        if not self._navigation.has_schedules():
            return ExportResult(
                success=False,
                message="No schedule to export.",
            )

        if getattr(self._navigation, "is_partial", False) is True:
            return ExportResult(
                success=False,
                message=(
                    "Temporary ranking previews cannot be exported as final "
                    "ranked results. Wait for ranking to complete."
                ),
            )

        # Read the currently displayed system from the navigation presenter:
        # it is the single source of truth for "which system the user picked".
        current_system = self._navigation.current_system()
        if current_system is None:
            return ExportResult(
                success=False,
                message="No schedule to export.",
            )

        outcome = self._service.export(current_system, output_path)
        if not outcome.success:
            return ExportResult(success=False, message=outcome.error_message)

        return ExportResult(
            success=True,
            message=f"Schedule saved to {outcome.path}.",
            path=outcome.path,
        )
