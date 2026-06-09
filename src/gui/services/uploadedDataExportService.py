"""Export service for uploaded input datasets (SCRUM-120).

The Version 2.0 GUI keeps uploaded data as parsed domain objects inside the
shared CacheManager. This service turns that cached state back into text files
that match the existing Version 1.0 input formats, then validates the generated
file by reading it with the matching project reader.

No customTkinter imports live here. The GUI chooses the destination path and
renders the returned ExportResult, while this service owns serialization,
validation, and error handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.cache_manager import CacheManager
from fileReader.baseFileReader import FileReaderFactory, FileReaderType
from gui.services.uploadService import UploadedInputData
from models import Course, ExamPeriod


@dataclass(frozen=True)
class ExportResult:
    """Result returned after attempting to export one uploaded dataset."""

    file_type: FileReaderType
    path: Path
    success: bool
    message: str
    item_count: int = 0


class UploadedDataExportService:
    """Writes uploaded datasets to downloadable text files."""

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        uploaded_data: UploadedInputData | None = None,
    ) -> None:
        """Create the service from cache and/or local upload state.

        Args:
            cache_manager: shared application cache. Preferred when supplied
                because it is the source of truth for uploaded data.
            uploaded_data: local upload snapshot used when no cache exists.
        """
        self._cache = cache_manager
        self._uploaded_data = uploaded_data or UploadedInputData()

    def export(self, file_type: FileReaderType, filepath: str | Path) -> ExportResult:
        """Export the requested dataset to ``filepath`` and validate the result."""
        path = Path(filepath)

        try:
            data = self._load_data(file_type)
            item_count = self._count_items(data)

            if item_count == 0:
                return ExportResult(
                    file_type=file_type,
                    path=path,
                    success=False,
                    message=f"No {self._display_name(file_type)} data available to export.",
                )

            content = self._serialize(file_type, data)
            self._write(path, content)
            self._validate_export(file_type, path, item_count)
        except (OSError, UnicodeError, ValueError) as error:
            return ExportResult(
                file_type=file_type,
                path=path,
                success=False,
                message=f"{self._display_name(file_type)} export failed: {error}",
            )

        return ExportResult(
            file_type=file_type,
            path=path,
            success=True,
            message=(
                f"{self._display_name(file_type)} exported successfully "
                f"({item_count} item{'s' if item_count != 1 else ''})."
            ),
            item_count=item_count,
        )

    def export_courses(self, filepath: str | Path) -> ExportResult:
        """Export uploaded courses to a courses-format text file."""
        return self.export(FileReaderType.COURSES, filepath)

    def export_programs(self, filepath: str | Path) -> ExportResult:
        """Export uploaded selected programs to a programs-format text file."""
        return self.export(FileReaderType.PROGRAMS, filepath)

    def export_exam_periods(self, filepath: str | Path) -> ExportResult:
        """Export uploaded exam periods to a dates-format text file."""
        return self.export(FileReaderType.EXAM_PERIODS, filepath)

    def _load_data(self, file_type: FileReaderType) -> Any:
        # Prefer cache-backed state because the rest of the application reads it.
        if self._cache is not None:
            if file_type == FileReaderType.COURSES:
                return list(self._cache.get_courses())
            if file_type == FileReaderType.PROGRAMS:
                return list(self._cache.get_selected_programs())
            if file_type == FileReaderType.EXAM_PERIODS:
                return list(self._cache.get_exam_periods())

        if file_type == FileReaderType.COURSES:
            return list(self._uploaded_data.courses or [])
        if file_type == FileReaderType.PROGRAMS:
            return list(self._uploaded_data.programs or [])
        if file_type == FileReaderType.EXAM_PERIODS:
            return list(self._uploaded_data.exam_periods or [])
        raise ValueError(f"Unsupported export file type: {file_type!r}")

    def _serialize(self, file_type: FileReaderType, data: Any) -> str:
        if file_type == FileReaderType.COURSES:
            return self._serialize_courses(data)
        if file_type == FileReaderType.PROGRAMS:
            return self._serialize_programs(data)
        if file_type == FileReaderType.EXAM_PERIODS:
            return self._serialize_exam_periods(data)
        raise ValueError(f"Unsupported export file type: {file_type!r}")

    @staticmethod
    def _serialize_courses(courses: list[Course]) -> str:
        blocks: list[str] = []
        for course in courses:
            lines = [
                "$$$$",
                course.name,
                course.course_number,
                course.instructor,
            ]
            for enrollment in course.programs:
                lines.append(
                    f"{enrollment.program_number},{enrollment.year},"
                    f"{enrollment.semester},{enrollment.status}"
                )
            lines.append(course.evaluation_type)
            blocks.append("\n".join(lines))
        return "\n".join(blocks) + "\n"

    @staticmethod
    def _serialize_programs(programs: list[str]) -> str:
        return ", ".join(programs) + "\n"

    @staticmethod
    def _serialize_exam_periods(exam_periods: list[ExamPeriod]) -> str:
        blocks: list[str] = []
        for exam_period in exam_periods:
            lines = [
                "$$$$",
                f"{exam_period.semester}, {exam_period.moed}",
                (
                    f"{exam_period.start_date.strftime('%d-%m-%Y')}, "
                    f"{exam_period.end_date.strftime('%d-%m-%Y')}"
                ),
            ]
            for excluded_date in sorted(exam_period.excluded_dates):
                lines.append(f"- {excluded_date.strftime('%d-%m-%Y')}")
            blocks.append("\n".join(lines))
        return "\n".join(blocks) + "\n"

    @staticmethod
    def _write(path: Path, content: str) -> None:
        # Parent directories are created so the user can choose a new export
        # folder from the save dialog without preparing it manually.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _validate_export(
        file_type: FileReaderType,
        path: Path,
        expected_count: int,
    ) -> None:
        # Reuse the existing readers for validation so exported files are proven
        # to be importable by the same workflow that created the data.
        reader = FileReaderFactory.get_reader(file_type)
        parsed = reader.read(path)
        actual_count = UploadedDataExportService._count_items(parsed)

        if actual_count != expected_count:
            raise ValueError(
                f"Export validation failed: expected {expected_count} item(s), "
                f"read back {actual_count}."
            )

    @staticmethod
    def _count_items(data: Any) -> int:
        try:
            return len(data)
        except TypeError:
            return 1

    @staticmethod
    def _display_name(file_type: FileReaderType) -> str:
        names = {
            FileReaderType.COURSES: "Courses file",
            FileReaderType.PROGRAMS: "Programs file",
            FileReaderType.EXAM_PERIODS: "Exam periods file",
        }
        return names.get(file_type, "Input file")
