from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Generic, TypeVar

# Generic return type used by all file readers.
# Each reader can return a different object type, such as list[str] or list[Course].
T = TypeVar("T")


class FileReaderType(Enum):
    """
    Defines the supported input file types in the system.

    Used by FileReaderFactory to create the correct reader implementation.
    """

    PROGRAMS = auto()     # Selected study programs file
    COURSES = auto()      # Courses data file
    EXAM_PERIODS = auto() # Exam periods and blocked dates file
    SCHEDULING_SETTINGS = auto()  # Part 3 optional settings file
    COMMANDS = auto()             # Snapshot and edit commands file (SCRUM-197)



class BaseFileReader(ABC, Generic[T]):
    """
    Base class for all file readers in the project.

    The reading flow is divided into:
    1. Path validation
    2. Loading raw file content
    3. Parsing content into domain objects
    """

    def read(self, filepath: str | Path) -> T:
        """
        Read and parse a file from the given path.

        Validates that the path exists and points to a regular file before
        loading and parsing the content.
        """
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path.is_file():
            raise ValueError(f"Path is not a regular file: {path}")

        raw = self.load(path)
        return self.parse(raw)

    def load(self, path: Path) -> str:
        """
        Load the raw file content as UTF-8 text.

        Subclasses may override this method if another format is needed.
        """
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @abstractmethod
    def parse(self, content: str) -> T:
        """
        Convert raw file content into structured objects.

        Every concrete file reader must implement this method.
        """
        ...  # Abstract method placeholder


class FileReaderFactory:
    """
    Creates the correct file reader according to the requested type.

    Centralizing reader creation keeps the rest of the project independent
    from concrete reader class names.
    """

    @staticmethod
    def get_reader(reader_type: FileReaderType) -> BaseFileReader:
        # Imports are placed here to avoid circular imports between readers.
        from fileReader.fileTypeReaders.programReader import ProgramsFileReader
        from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
        from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
        from fileReader.fileTypeReaders.schedulingSettingsReader import SchedulingSettingsFileReader
        from fileReader.fileTypeReaders.commandsFileReader import CommandsFileReader
        
        # Maps each file type to its matching reader implementation.
        registry: dict[FileReaderType, type[BaseFileReader]] = {
            FileReaderType.PROGRAMS:            ProgramsFileReader,
            FileReaderType.COURSES:             CoursesFileReader,
            FileReaderType.EXAM_PERIODS:        ExamPeriodsFileReader,
            FileReaderType.SCHEDULING_SETTINGS: SchedulingSettingsFileReader,
            FileReaderType.COMMANDS:            CommandsFileReader,
        }

        cls = registry.get(reader_type)

        if cls is None:
            raise ValueError(f"No reader registered for type: {reader_type!r}")

        return cls()
