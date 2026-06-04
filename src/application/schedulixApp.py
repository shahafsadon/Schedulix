from dataclasses import dataclass
from pathlib import Path

from fileReader.baseFileReader import (
    FileReaderFactory,
    FileReaderType,
)
from output.outputWriter import (
    DEFAULT_OUTPUT_PATH,
    OutputWriter,
)
from scheduling.courseFilter import (
    CourseFilter,
)
from scheduling.examScheduleGenerator import (
    ExamScheduleGenerator,
)


# Project root is resolved from this file so PyCharm and terminal runs behave
# the same even when their working directories are different.
PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

# Default input files for the simple Version 1.0 flow.
DEFAULT_COURSES_PATH = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "CourseExample.txt"
)

DEFAULT_EXAM_PERIODS_PATH = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "DatesExample.txt"
)

DEFAULT_PROGRAMS_PATH = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "ProgramsExample.txt"
)

DEFAULT_APP_OUTPUT_PATH = (
    PROJECT_ROOT
    / DEFAULT_OUTPUT_PATH
)


@dataclass(frozen=True)
class ApplicationResult:
    """Stores a short summary of one completed application run."""

    selected_program_count: int
    total_course_count: int
    relevant_course_count: int
    exam_period_count: int
    schedule_count: int
    output_path: Path


class SchedulixApp:
    """Runs the complete file-based Version 1.0 application flow."""

    def __init__(
        self,
        course_filter: CourseFilter | None = None,
        schedule_generator: ExamScheduleGenerator | None = None,
        output_writer: OutputWriter | None = None,
    ) -> None:
        self.course_filter = (
            course_filter
            or CourseFilter()
        )

        self.schedule_generator = (
            schedule_generator
            or ExamScheduleGenerator()
        )

        self.output_writer = (
            output_writer
            or OutputWriter()
        )

    def run(
        self,
        courses_path: str | Path = DEFAULT_COURSES_PATH,
        exam_periods_path: str | Path = DEFAULT_EXAM_PERIODS_PATH,
        programs_path: str | Path = DEFAULT_PROGRAMS_PATH,
        output_path: str | Path = DEFAULT_APP_OUTPUT_PATH,
    ) -> ApplicationResult:
        """
        Read input files, generate schedules lazily, and stream the output.
        """
        programs_reader = (
            FileReaderFactory.get_reader(
                FileReaderType.PROGRAMS
            )
        )

        selected_programs = (
            programs_reader.read(
                programs_path
            )
        )

        courses_reader = (
            FileReaderFactory.get_reader(
                FileReaderType.COURSES
            )
        )

        courses = (
            courses_reader.read(
                courses_path
            )
        )

        periods_reader = (
            FileReaderFactory.get_reader(
                FileReaderType.EXAM_PERIODS
            )
        )

        exam_periods = (
            periods_reader.read(
                exam_periods_path
            )
        )

        relevant_courses = (
            self.course_filter.filter_relevant_courses(
                courses,
                selected_programs,
            )
        )

        # Do not call generate_exam_systems() here.
        #
        # That compatibility method deliberately returns a list and would
        # retain the complete Cartesian product. The iterator allows the
        # writer to consume one system at a time and write it directly to disk.
        schedules = (
            self.schedule_generator.iter_exam_systems(
                relevant_courses,
                exam_periods,
            )
        )

        (
            created_output_path,
            schedule_count,
        ) = (
            self.output_writer.write_with_count(
                schedules,
                output_path,
            )
        )

        return ApplicationResult(
            selected_program_count=len(
                selected_programs
            ),
            total_course_count=len(
                courses
            ),
            relevant_course_count=len(
                relevant_courses
            ),
            exam_period_count=len(
                exam_periods
            ),
            schedule_count=schedule_count,
            output_path=created_output_path,
        )