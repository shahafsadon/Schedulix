from pathlib import Path

from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


# Default location required by the Jira task.
DEFAULT_OUTPUT_PATH = Path("data") / "outputs" / "exam_schedules.txt"

# All output dates must use the format defined in the output format document.
DATE_FORMAT = "%d-%m-%Y"

# A simple separator keeps each schedule easy to read in a text file.
TITLE_LINE = "========================================"

# Stable ordering for the sections required by the specification.
SEMESTER_ORDER = {"FALL": 0, "SPRI": 1, "SUMM": 2}
MOED_ORDER = {"Aleph": 0, "Bet": 1, "Gimel": 2}


class OutputWriter:
    """
    Writes generated exam schedules into a readable text file.

    The writer does not create schedules and does not validate conflicts. Its
    only responsibility is formatting valid schedules that were already created
    by the scheduling layer.
    """

    def write(
        self,
        schedules: list[ExamSystem],
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

    def format_schedules(self, schedules: list[ExamSystem]) -> str:
        """
        Convert schedules into the final text format.

        Each Schedule block represents one complete exam-system option. Inside
        it, exams are separated by semester and moed and sorted by date.
        """
        # Start the file with a clear project title.
        lines = [
            "Schedulix Exam Schedules",
            TITLE_LINE,
        ]

        # Add every schedule to the file, numbered from 1.
        for index, schedule in enumerate(schedules, start=1):
            lines.extend(self._format_schedule(index, schedule))
        # Join all lines into one text block and end the file with a newline.
        return "\n".join(lines) + "\n"

    def _format_schedule(self, index: int, schedule: ExamSystem) -> list[str]:
        """Format one complete exam-system option."""
        # Each schedule starts with its number.
        lines = [
            "",
            f"Schedule {index}",
            TITLE_LINE,
        ]

        current_semester: str | None = None

        for period_schedule in sorted(
            schedule.period_schedules,
            key=self._period_sort_key,
        ):
            if period_schedule.semester != current_semester:
                lines.append(f"Semester: {period_schedule.semester}")
                current_semester = period_schedule.semester

            lines.append(f"Moed: {period_schedule.moed}")

            # Sort exams by date first, then by course number for stable output.
            for exam in sorted(
                period_schedule.scheduled_exams,
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

    @staticmethod
    def _period_sort_key(schedule: ExamSchedule) -> tuple[int, int, str, str]:
        """Sort period sections by semester and moed in requirement order."""
        return (
            SEMESTER_ORDER.get(schedule.semester, len(SEMESTER_ORDER)),
            MOED_ORDER.get(schedule.moed, len(MOED_ORDER)),
            schedule.semester,
            schedule.moed,
        )
