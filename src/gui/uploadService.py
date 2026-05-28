from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fileReader.baseFileReader import FileReaderFactory, FileReaderType
from models import Course, ExamPeriod


@dataclass(frozen=True)
class UploadResult:
    """
    Result returned after trying to load one input file.

    The GUI can use this object directly to show clear upload feedback without
    knowing the details of the file-reader implementations.
    """

    file_type: FileReaderType
    path: Path
    success: bool
    message: str
    item_count: int = 0
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
    the relevant reader, stores the parsed data after success, and returns a
    friendly result object for the screen to display.
    """

    uploaded_data: UploadedInputData = field(default_factory=UploadedInputData)

    def upload(self, file_type: FileReaderType, filepath: str | Path) -> UploadResult:
        """Load and parse one file according to its expected file type."""
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
            )

        # Store only successfully parsed data. Failed uploads leave the previous
        # valid state untouched for the next screens.
        self._store(file_type, data)
        item_count = self._count_items(data)

        # Return both the parsed data and a short summary for upload feedback.
        return UploadResult(
            file_type=file_type,
            path=path,
            success=True,
            message=(
                f"{self._display_name(file_type)} loaded successfully "
                f"({item_count} item{'s' if item_count != 1 else ''})."
            ),
            item_count=item_count,
            data=data,
        )

    def upload_courses(self, filepath: str | Path) -> UploadResult:
        """Load a courses file."""
        return self.upload(FileReaderType.COURSES, filepath)

    def upload_programs(self, filepath: str | Path) -> UploadResult:
        """Load a selected-programs file."""
        return self.upload(FileReaderType.PROGRAMS, filepath)

    def upload_exam_periods(self, filepath: str | Path) -> UploadResult:
        """Load an exam-periods file."""
        return self.upload(FileReaderType.EXAM_PERIODS, filepath)

    def get_uploaded_data(self) -> UploadedInputData:
        """Return the current parsed data snapshot."""
        return self.uploaded_data

    def is_ready_for_scheduling(self) -> bool:
        """Return True when courses, programs, and exam periods are loaded."""
        return self.uploaded_data.is_complete()

    def _store(self, file_type: FileReaderType, data: Any) -> None:
        # Keep each parsed file in the matching field so later screens can read
        # one shared upload snapshot.
        if file_type == FileReaderType.COURSES:
            self.uploaded_data.courses = data
        elif file_type == FileReaderType.PROGRAMS:
            self.uploaded_data.programs = data
        elif file_type == FileReaderType.EXAM_PERIODS:
            self.uploaded_data.exam_periods = data
        else:
            raise ValueError(f"Unsupported upload file type: {file_type!r}")

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
