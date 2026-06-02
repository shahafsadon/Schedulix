"""Export service for writing a single chosen exam system to a file (SCRUM-127).

Version 1.0 already knows how to write generated schedules to a text file via
OutputWriter. SCRUM-127 reuses that writer rather than duplicating any format
logic; this service just wraps OutputWriter to:

- accept a SINGLE ExamSystem (the one the user selected on the navigation
  screen), not the full list of systems, since the user exports the option they
  picked, not every option;
- expose a small, GUI-friendly outcome (ExportOutcome) so the presenter does
  not need to handle file-system exceptions itself.

No GUI imports live here: the service is fully unit-testable on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from output.outputWriter import OutputWriter
from scheduling.examScheduleGenerator import ExamSystem


@dataclass(frozen=True)
class ExportOutcome:
    """Result of a single export attempt, returned to the presenter.

    `path` is the location of the written file on success; on failure it is
    None and `error_message` explains what happened (typically an OS error
    such as a permission problem or an invalid path).
    """

    success: bool
    path: Path | None = None
    error_message: str = ""


class ExportService:
    """Writes one chosen exam system to a user-specified file."""

    def __init__(self, output_writer: OutputWriter | None = None) -> None:
        """Create the service, optionally with a custom OutputWriter.

        Args:
            output_writer: reuses the Version 1.0 writer; tests can inject a
                fake to avoid touching the file system, while application code
                relies on the default.
        """
        # Reuse the v1.0 writer so the GUI export matches the v1.0 output 1:1.
        self._output_writer = output_writer or OutputWriter()

    def export(self, system: ExamSystem, output_path: str | Path) -> ExportOutcome:
        """Write `system` to `output_path` and return a display-ready outcome.

        The user selects exactly one system on the navigation screen; the
        OutputWriter API still expects a list, so we wrap it in a single-element
        list. File-system errors (permission denied, invalid path, disk full)
        are caught here so the presenter can simply show the message.
        """
        # OutputWriter is list-based, so wrap the single chosen system.
        try:
            written_path = self._output_writer.write([system], output_path)
        except OSError as error:
            # Most realistic failure mode: the path is unwritable or invalid.
            return ExportOutcome(
                success=False,
                error_message=f"Could not write file: {error.strerror or error}",
            )
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            # Defensive: any unexpected error still produces a clean outcome
            # rather than bubbling up and crashing the GUI.
            return ExportOutcome(
                success=False,
                error_message=(
                    f"Export failed unexpectedly: {type(error).__name__}."
                ),
            )

        return ExportOutcome(success=True, path=written_path)