from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from application.cache_manager import CacheManager
from fileReader.baseFileReader import FileReaderFactory, FileReaderType
from models import Course, ExamPeriod


class UploadMode(Enum):
    """
    Describes how newly uploaded data should affect existing application state.

    ``REPLACE`` discards the current dataset of the same type and stores the
    uploaded file as the new source of truth. ``APPEND`` keeps the current data
    and adds the newly parsed items on top of it.
    """

    REPLACE = "replace"
    APPEND = "append"

    @property
    def display_name(self) -> str:
        """Return a short label suitable for status messages."""
        return self.value.capitalize()


@dataclass(frozen=True)
class UploadResult:
    """
    Result returned after trying to load one input file.

    The GUI can use this object directly to show clear upload feedback without
    knowing the details of the file-reader implementations. ``item_count`` is
    the number of records parsed from the selected file, while
    ``cached_count`` is the total number now stored for that dataset.
    """

    file_type: FileReaderType
    path: Path
    success: bool
    message: str
    mode: UploadMode = UploadMode.REPLACE
    item_count: int = 0
    cached_count: int = 0
    data: Any | None = None


@dataclass
class UploadedInputData:
    """Holds the latest parsed input data loaded by the upload workflow."""

    courses: list[Course] | None = None
    programs: list[str] | None = None
    exam_periods: list[ExamPeriod] | None = None

    def is_complete(self) -> bool:
        """Return True when all required input files were loaded successfully."""
        return (
            self.courses is not None
            and self.programs is not None
            and self.exam_periods is not None
        )


@dataclass
class FileUploadService:
    """
    Connects the GUI upload workflow to the existing file readers.

    This class owns no visual behavior. It validates the selected file by using
    the relevant reader, stores the parsed data after success, applies either a
    replace or append operation to the shared cache when one is injected, and
    returns a friendly result object for the screen to display.
    """

    uploaded_data: UploadedInputData = field(default_factory=UploadedInputData)
    cache_manager: CacheManager | None = None

    def __post_init__(self) -> None:
        """
        Seed the upload snapshot from the cache when persisted data exists.

        The cache is the long-lived application state, while ``uploaded_data``
        is the screen-friendly snapshot used by the upload workflow. Keeping
        them aligned lets a restarted GUI show that data is already available.
        """
        if self.cache_manager is None:
            return

        courses = self.cache_manager.get_courses()
        programs = self.cache_manager.get_selected_programs()
        exam_periods = self.cache_manager.get_exam_periods()

        if self.uploaded_data.courses is None and courses:
            self.uploaded_data.courses = list(courses)
        if self.uploaded_data.programs is None and programs:
            self.uploaded_data.programs = list(programs)
        if self.uploaded_data.exam_periods is None and exam_periods:
            self.uploaded_data.exam_periods = list(exam_periods)

    def upload(
        self,
        file_type: FileReaderType,
        filepath: str | Path,
        mode: UploadMode = UploadMode.REPLACE,
    ) -> UploadResult:
        """Load, parse, and apply one file according to its update mode."""
        # Convert the selected file into a Path so the service accepts strings
        # from the GUI and Path objects from tests.
        path = Path(filepath)

        # Use the existing factory so the GUI does not depend on concrete
        # reader classes such as CoursesFileReader or ExamPeriodsFileReader.
        reader = FileReaderFactory.get_reader(file_type)

        # Reader errors are converted into UploadResult objects so the screen
        # can show a friendly message instead of crashing the application.
        try:
            data = reader.read(path)
        except (OSError, UnicodeError, ValueError) as error:
            return UploadResult(
                file_type=file_type,
                path=path,
                success=False,
                message=f"{self._display_name(file_type)} upload failed: {error}",
                mode=mode,
                cached_count=self._current_count(file_type),
            )

        # Update the cache first. A conflicting append must not also change
        # the local screen snapshot when the cache rejects it.
        try:
            self._sync_cache(file_type, data, mode)
        except ValueError as error:
            return UploadResult(
                file_type=file_type,
                path=path,
                success=False,
                message=f"{self._display_name(file_type)} upload failed: {error}",
                mode=mode,
                cached_count=self._current_count(file_type),
            )

        # Store only successfully parsed data. Failed uploads leave both the
        # local snapshot and the shared cache untouched for the next screens.
        self._store(file_type, data, mode)
        if self.cache_manager is not None and file_type == FileReaderType.COURSES:
            # CacheManager merges repeat course uploads, so mirror its clean
            # source of truth in the upload screen as well.
            self.uploaded_data.courses = list(self.cache_manager.get_courses())
        item_count = self._count_items(data)
        cached_count = self._current_count(file_type)

        # Return both the parsed data and a short summary for upload feedback.
        return UploadResult(
            file_type=file_type,
            path=path,
            success=True,
            message=(
                f"{self._display_name(file_type)} {mode.value} completed "
                f"({item_count} item{'s' if item_count != 1 else ''}, "
                f"{cached_count} total)."
            ),
            mode=mode,
            item_count=item_count,
            cached_count=cached_count,
            data=data,
        )

    def upload_courses(
        self,
        filepath: str | Path,
        mode: UploadMode = UploadMode.REPLACE,
    ) -> UploadResult:
        """Load a courses file."""
        return self.upload(FileReaderType.COURSES, filepath, mode)

    def upload_programs(
        self,
        filepath: str | Path,
        mode: UploadMode = UploadMode.REPLACE,
    ) -> UploadResult:
        """Load a selected-programs file."""
        return self.upload(FileReaderType.PROGRAMS, filepath, mode)

    def upload_exam_periods(
        self,
        filepath: str | Path,
        mode: UploadMode = UploadMode.REPLACE,
    ) -> UploadResult:
        """Load an exam-periods file."""
        return self.upload(FileReaderType.EXAM_PERIODS, filepath, mode)

    def get_uploaded_data(self) -> UploadedInputData:
        """Return the current parsed data snapshot."""
        return self.uploaded_data

    def is_ready_for_scheduling(self) -> bool:
        """Return True when courses, programs, and exam periods are loaded."""
        return self.uploaded_data.is_complete()

    def _store(self, file_type: FileReaderType, data: Any, mode: UploadMode) -> None:
        # Keep each parsed file in the matching field so later screens can read
        # one shared upload snapshot. Append mode mirrors the cache operation.
        if file_type == FileReaderType.COURSES:
            self.uploaded_data.courses = self._apply_mode(
                self.uploaded_data.courses,
                data,
                mode,
            )
        elif file_type == FileReaderType.PROGRAMS:
            self.uploaded_data.programs = self._apply_mode(
                self.uploaded_data.programs,
                data,
                mode,
                unique=True,
            )
        elif file_type == FileReaderType.EXAM_PERIODS:
            self.uploaded_data.exam_periods = self._apply_mode(
                self.uploaded_data.exam_periods,
                data,
                mode,
            )
        else:
            raise ValueError(f"Unsupported upload file type: {file_type!r}")

    def _sync_cache(
        self,
        file_type: FileReaderType,
        data: Any,
        mode: UploadMode,
    ) -> None:
        # When a CacheManager is injected, successful uploads immediately update
        # persisted application state so later wizard screens see the same data.
        if self.cache_manager is None:
            return

        if file_type == FileReaderType.COURSES:
            if mode == UploadMode.APPEND:
                self.cache_manager.add_courses(data)
            else:
                self.cache_manager.set_courses(data)
        elif file_type == FileReaderType.PROGRAMS:
            if mode == UploadMode.APPEND:
                self.cache_manager.add_selected_programs(data)
            else:
                self.cache_manager.set_selected_programs(data)
        elif file_type == FileReaderType.EXAM_PERIODS:
            if mode == UploadMode.APPEND:
                self.cache_manager.add_exam_periods(data)
            else:
                self.cache_manager.set_exam_periods(data)
        else:
            raise ValueError(f"Unsupported upload file type: {file_type!r}")

        # Any input-data change makes previously generated schedules stale.
        self.cache_manager.invalidate_generated_schedules()

    def _current_count(self, file_type: FileReaderType) -> int:
        # Prefer the shared cache count when it exists, because that is the
        # application state later screens consume. Fall back to the local
        # snapshot for tests or standalone upload screens.
        if self.cache_manager is not None:
            if file_type == FileReaderType.COURSES:
                return len(self.cache_manager.get_courses())
            if file_type == FileReaderType.PROGRAMS:
                return len(self.cache_manager.get_selected_programs())
            if file_type == FileReaderType.EXAM_PERIODS:
                return len(self.cache_manager.get_exam_periods())

        if file_type == FileReaderType.COURSES:
            return self._count_items(self.uploaded_data.courses or [])
        if file_type == FileReaderType.PROGRAMS:
            return self._count_items(self.uploaded_data.programs or [])
        if file_type == FileReaderType.EXAM_PERIODS:
            return self._count_items(self.uploaded_data.exam_periods or [])
        raise ValueError(f"Unsupported upload file type: {file_type!r}")

    @staticmethod
    def _apply_mode(
        current: list | None,
        new_data: list,
        mode: UploadMode,
        unique: bool = False,
    ) -> list:
        # Replace is a fresh list so external readers cannot mutate the stored
        # snapshot after the upload service returns.
        if mode == UploadMode.REPLACE:
            return FileUploadService._dedupe(new_data) if unique else list(new_data)

        combined = list(current or []) + list(new_data)
        return FileUploadService._dedupe(combined) if unique else combined

    @staticmethod
    def _dedupe(items: list) -> list:
        """Return ``items`` without duplicates while preserving first-seen order."""
        unique_items: list = []
        seen = set()
        for item in items:
            if item in seen:
                continue
            unique_items.append(item)
            seen.add(item)
        return unique_items

    @staticmethod
    def _count_items(data: Any) -> int:
        # All current readers return lists, but this keeps the service safe if a
        # future reader returns a single object.
        try:
            return len(data)
        except TypeError:
            return 1

    @staticmethod
    def _display_name(file_type: FileReaderType) -> str:
        # User-facing names keep GUI messages readable and avoid exposing enum
        # names such as FileReaderType.EXAM_PERIODS.
        names = {
            FileReaderType.COURSES: "Courses file",
            FileReaderType.PROGRAMS: "Programs file",
            FileReaderType.EXAM_PERIODS: "Exam periods file",
        }
        return names.get(file_type, "Input file")
