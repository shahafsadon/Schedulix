from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Generic, TypeVar

# T is the return type of a reader — list[str], list[Course], etc.
# Using a TypeVar lets type checkers understand what each concrete reader returns
# without us having to write separate overloads for every subclass.
T = TypeVar("T")


class FileReaderType(Enum):
    """
    Identifies which kind of input file we want to read.

    Used by FileReaderFactory so callers can request a reader by intent
    ("I need to read the courses file") rather than by class name.
    This makes it easy to swap implementations later without touching call sites.
    """

    PROGRAMS = auto()     # The file listing which study programs are in scope
    COURSES = auto()      # The file describing all courses and their details
    EXAM_PERIODS = auto() # The file defining allowed exam windows and blocked dates


class BaseFileReader(ABC, Generic[T]):
    """
    The common interface that all file readers share.

    Responsibilities are split across three methods so that each concern
    can be overridden independently:

        read(filepath)  — the public entry point; validates the path,
                          then calls load() and parse() in sequence.
                          Subclasses should not normally need to touch this.

        load(path)      — raw I/O: opens the file and returns its contents.
                          The default implementation reads a UTF-8 text file.
                          Override this if your format needs something different
                          (e.g. binary mode for Excel, a CSV reader, an HTTP
                          fetch, etc.) without touching any parsing logic.

        parse(content)  — interprets whatever load() returned and produces
                          the typed result. This is the only method our current
                          readers implement, and that stays unchanged.

    This separation means:
      - Adding a new *file format* (e.g. JSON) only requires overriding load().
      - Adding a new *data type* (e.g. rooms, students) only requires a new
        parse() in a new subclass.
      - Both concerns are independently testable without touching the filesystem.
    """

    def read(self, filepath: str | Path) -> T:
        """
        Validate the path, load the file, parse the contents, and return the result.

        This is the only method callers need. It intentionally does very little
        itself — path validation is here because it belongs to neither load()
        nor parse(), and centralizing it means every reader gets the same clear
        error messages for free.

        Raises:
            FileNotFoundError: If nothing exists at the given path.
            ValueError:        If the path exists but is not a regular file.
            OSError:           For any other filesystem-level failure.
        """
        path = Path(filepath)  # Normalize so both str and Path inputs work

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            # Catches directories, device files, and other non-file paths
            raise ValueError(f"Path is not a regular file: {path}")

        raw = self.load(path)
        return self.parse(raw)

    def load(self, path: Path) -> str:
        """
        Open the file and return its raw contents as a string.

        The default reads a plain UTF-8 text file, which covers all of our
        current .txt formats. Subclasses can override this to handle other
        formats without changing any parsing logic. For example:

            Binary file:
                with open(path, "rb") as f:
                    return f.read()          # parse() would then receive bytes

            CSV (pre-parsed into rows):
                import csv
                with open(path, newline="", encoding="utf-8") as f:
                    return list(csv.DictReader(f))

            JSON (pre-parsed into a dict/list):
                import json
                with open(path, encoding="utf-8") as f:
                    return json.load(f)

        Note: if load() returns something other than str, update parse()'s
        type annotation to match.
        """
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @abstractmethod
    def parse(self, content: str) -> T:
        """
        Convert the raw content returned by load() into a typed result.

        Subclasses must implement this. The type of `content` matches
        whatever load() returns — str by default, but a subclass that
        overrides load() to return bytes (or a dict, or a list of rows)
        should update this signature accordingly.
        """
        ...


class FileReaderFactory:
    """
    Creates the right reader for a given file type.

    Instead of scattering `if file_type == "courses": reader = CoursesFileReader()`
    logic across the codebase, callers ask the factory and get back a ready-to-use
    reader. Adding support for a new file type only requires updating the registry
    inside `get_reader` — nothing else changes.

    Usage:
        reader = FileReaderFactory.get_reader(FileReaderType.COURSES)
        courses = reader.read("data/courses.txt")
    """

    @staticmethod
    def get_reader(reader_type: FileReaderType) -> BaseFileReader:
        # Imports are deferred to inside the method to avoid circular imports.
        # Each reader module imports from base.py, so importing them at module
        # level here would create an import cycle.
        from fileReader.fileTypeReaders.programReader import ProgramsFileReader
        from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
        from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader

        # Map each enum value to the class that knows how to handle it.
        # A dict is used instead of if/elif so that adding a new type
        # is a one-line change and nothing can accidentally fall through.
        registry: dict[FileReaderType, type[BaseFileReader]] = {
            FileReaderType.PROGRAMS:     ProgramsFileReader,
            FileReaderType.COURSES:      CoursesFileReader,
            FileReaderType.EXAM_PERIODS: ExamPeriodsFileReader,
        }

        cls = registry.get(reader_type)
        if cls is None:
            # This should only happen if someone adds a new enum value
            # but forgets to register it here — the message points them
            # straight to the fix.
            raise ValueError(f"No reader registered for type: {reader_type!r}")

        return cls()