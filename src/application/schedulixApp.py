from dataclasses import dataclass
from pathlib import Path

from fileReader.baseFileReader import FileReaderFactory, FileReaderType
from output.outputWriter import DEFAULT_OUTPUT_PATH, OutputWriter
from scheduling.courseFilter import CourseFilter
from scheduling.examScheduleGenerator import ExamScheduleGenerator


# Default input files for the simple Version 1.0 flow.
DEFAULT_COURSES_PATH = Path("data") / "examples" / "CourseExample.txt"
DEFAULT_EXAM_PERIODS_PATH = Path("data") / "examples" / "DatesExample.txt"
DEFAULT_PROGRAMS_PATH = Path("data") / "examples" / "ProgramsExample.txt"


@dataclass(frozen=True)
class ApplicationResult:
    """
    Stores a short summary of one application run.

    This helps main.py print clear information after the output file is written.
    It also helps tests check that the full flow really worked.
    """

    selected_program_count: int
    total_course_count: int
    relevant_course_count: int
    exam_period_count: int
    schedule_count: int
    output_path: Path


class SchedulixApp:
    """
    Runs the full application flow.

    The class connects the project parts in order:
    read input files, filter courses, generate schedules, and write output.
    """

    def __init__(
        self,
        course_filter: CourseFilter | None = None,
        schedule_generator: ExamScheduleGenerator | None = None,
        output_writer: OutputWriter | None = None,
    ) -> None:
        """
        Create the app with the services it needs.

        The parameters are optional so tests can replace services if needed.
        In the regular run, the default project services are used.
        """
        # Use the real course filter unless another one was provided.
        self.course_filter = course_filter or CourseFilter()
        # Use the real schedule generator unless another one was provided.
        self.schedule_generator = schedule_generator or ExamScheduleGenerator()
        # Use the real output writer unless another one was provided.
        self.output_writer = output_writer or OutputWriter()

    def run(
        self,
        courses_path: str | Path = DEFAULT_COURSES_PATH,
        exam_periods_path: str | Path = DEFAULT_EXAM_PERIODS_PATH,
        programs_path: str | Path = DEFAULT_PROGRAMS_PATH,
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
    ) -> ApplicationResult:
        """
        Run the full flow from input files to output file.
        """
        # Read the selected program numbers.
        programs_reader = FileReaderFactory.get_reader(FileReaderType.PROGRAMS)
        selected_programs = programs_reader.read(programs_path)
        # Read all courses from the courses file.
        courses_reader = FileReaderFactory.get_reader(FileReaderType.COURSES)
        courses = courses_reader.read(courses_path)
        # Read all exam periods and excluded dates.
        periods_reader = FileReaderFactory.get_reader(FileReaderType.EXAM_PERIODS)
        exam_periods = periods_reader.read(exam_periods_path)

        # Keep only courses that belong to selected programs and use Exam.
        relevant_courses = self.course_filter.filter_relevant_courses(
            courses,
            selected_programs,
        )
        # Generate valid schedules for the relevant courses.
        schedules = self.schedule_generator.generate_for_periods(
            relevant_courses,
            exam_periods,
        )

        # Write the generated schedules to the output file.
        created_output_path = self.output_writer.write(schedules, output_path)

        # Return a small summary of the completed run.
        return ApplicationResult(
            selected_program_count=len(selected_programs),
            total_course_count=len(courses),
            relevant_course_count=len(relevant_courses),
            exam_period_count=len(exam_periods),
            schedule_count=len(schedules),
            output_path=created_output_path,
        )
