from pathlib import Path

from scheduling.examScheduleGenerator import ExamSchedule


# Default location required by the Jira task.
DEFAULT_OUTPUT_PATH = Path("data") / "outputs" / "exam_schedules.txt"

# All output dates must use the format defined in the output format document.
DATE_FORMAT = "%d-%m-%Y"

# A simple separator keeps each schedule easy to read in a text file.
TITLE_LINE = "========================================"


class OutputWriter:
    """
    Writes generated exam schedules into a readable text file.

    The writer does not create schedules and does not validate conflicts. Its
    only responsibility is formatting valid schedules that were already created
    by the scheduling layer.
    """

    def write(
        self,
        schedules: list[ExamSchedule],
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
    ) -> Path:
        """
        Write all schedules to a text file and return the created file path.

        The output directory is created if it does not exist. Exams inside each
        schedule are sorted by date, then by course number
        """
        # Convert string paths into Path objects so both input styles work.
        path = Path(output_path)

        # Create the output directory if it does not exist yet.
        path.parent.mkdir(parents=True, exist_ok=True)

        # Build the text content and write it as a UTF-8 file.
        path.write_text(self.format_schedules(schedules), encoding="utf-8")

        # Return the path so callers or tests can know where the file was saved.
        return path

    def format_schedules(self, schedules: list[ExamSchedule]) -> str:
        """
        Convert schedules into the final text format.

        Each schedule has a title, then one semester section and one moed
        section. This matches the current ExamSchedule model, where each object
        represents one schedule option for one exam period.
        """
        # Start the file with a clear project title.
        lines = [
            TITLE_LINE,
        ]

        # Add every schedule to the file, numbered from 1.
        for index, schedule in enumerate(schedules, start=1):
            lines.extend(self._format_schedule(index, schedule))

        # Join all lines into one text block and end the file with a newline.
        return "\n".join(lines) + "\n"

    def _format_schedule(self, index: int, schedule: ExamSchedule) -> list[str]:
        """Format one schedule option."""
        # Each schedule starts with its number, semester, and moed.
        lines = [
            "",
            f"Schedule {index}",
            TITLE_LINE,
            f"Semester: {schedule.semester}",
            f"Moed: {schedule.moed}",
        ]

        # Sort exams by date first, then by course number for stable output.
        for exam in sorted(
            schedule.scheduled_exams,
            key=lambda item: (item.exam_date, item.course.course_number),
        ):
            # One exam is written in one readable line.
            lines.append(
                f"{exam.exam_date.strftime(DATE_FORMAT)} | "
                f"{exam.course.name} | "
                f"{exam.course.instructor}"
            )

        # Return the formatted lines so the caller can add them to the full file.
        return lines
