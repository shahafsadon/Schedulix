from fileReader.baseFileReader import BaseFileReader
from models import Course, ProgramEnrollment

# Records in the courses file are separated by this marker.
# Using $$$$ (rather than, say, a blank line) makes it unambiguous even
# when course names or instructor names contain blank lines by accident.
SEPARATOR = "$$$$"


class CoursesFileReader(BaseFileReader[list[Course]]):
    """
    Reads the courses input file and returns a list of Course objects.

    The file uses $$$$ as a record separator. Each record looks like this:

        $$$$
        Physics 1
        83102
        Prof. O. Some
        83101,1,FALL,Obligatory
        83102,1,FALL,Obligatory
        Exam

    Line order within a record is fixed:
        1. Course name
        2. Course number
        3. Instructor name
        4..N-1. Program enrollment lines (one per program that includes this course)
        N. Evaluation type (last line)

    The number of enrollment lines is variable, which is why we read the first
    three lines and the last line by position, and treat everything in between
    as enrollments.
    """

    def parse(self, content: str) -> list[Course]:
        """Split the file into records and parse each one."""
        # Splitting on the separator naturally produces an empty string before
        # the very first $$$$ — the `if not block` guard below discards it.
        blocks = content.split(SEPARATOR)
        courses: list[Course] = []

        for block in blocks:
            block = block.strip()
            if not block:
                # Skip the empty fragment that appears before the first $$$$ marker
                continue
            courses.append(self._parse_block(block))

        return courses

    # ------------------------------------------------------------------
    # Internal helpers — these are implementation details, not public API
    # ------------------------------------------------------------------

    def _parse_block(self, block: str) -> Course:
        """
        Parse a single course record (the text between two $$$$ markers).

        We strip and filter blank lines so that trailing newlines or accidental
        extra blank lines inside a record don't shift the positional parsing.
        """
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

        # A valid record needs at least: name, number, instructor,
        # one enrollment line, and an evaluation type = 5 lines minimum.
        # We check for 4 here (one enrollment + eval share the "last slot"),
        # and the enrollment-specific check below catches the truly empty case.
        if len(lines) < 4:
            raise ValueError(
                f"Malformed course block — expected at least 4 lines, "
                f"got {len(lines)}:\n{block}"
            )

        # Fixed positions: first three lines are always name, number, instructor
        name            = lines[0]
        course_number   = lines[1]
        instructor      = lines[2]

        # Last line is always the evaluation type
        evaluation_type = lines[-1]

        # Everything between instructor (index 2) and the last line is enrollments.
        # Slicing [3:-1] handles any number of enrollment lines, including one.
        enrollment_lines = lines[3:-1]
        if not enrollment_lines:
            raise ValueError(
                f"Course '{name}' ({course_number}) has no program enrollment lines."
            )

        programs = [self._parse_enrollment(ln) for ln in enrollment_lines]

        return Course(
            name=name,
            course_number=course_number,
            instructor=instructor,
            programs=programs,
            evaluation_type=evaluation_type,
        )

    @staticmethod
    def _parse_enrollment(line: str) -> ProgramEnrollment:
        """
        Parse one enrollment line into a ProgramEnrollment object.

        Expected format: <program_number>,<year>,<semester>,<status>
        Example:         83101,1,FALL,Obligatory
        """
        parts = [p.strip() for p in line.split(",")]

        if len(parts) != 4:
            raise ValueError(
                f"Malformed enrollment line — expected 4 comma-separated fields, "
                f"got {len(parts)}: '{line}'"
            )

        program_number, year_str, semester, status = parts

        # year_str should always be a digit, but we give a helpful message
        # if the file has something unexpected (e.g. "one" instead of "1")
        try:
            year = int(year_str)
        except ValueError:
            raise ValueError(
                f"Non-integer year in enrollment line: '{year_str}' (full line: '{line}')"
            )

        return ProgramEnrollment(
            program_number=program_number,
            year=year,
            semester=semester,
            status=status,
        )