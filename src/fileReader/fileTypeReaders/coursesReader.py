from fileReader.baseFileReader import BaseFileReader
from models import Course, ProgramEnrollment

# Marker used to separate course records inside the input file.
SEPARATOR = "$$$$"

# Allowed values according to the project input specification.
VALID_YEARS = {1, 2, 3, 4}
VALID_SEMESTERS = {"FALL", "SPRI", "SUMM"}
VALID_STATUSES = {"Obligatory", "Elective"}
VALID_EVALUATION_TYPES = {"Exam", "Project", "Attendance"}


class CoursesFileReader(BaseFileReader[list[Course]]):
    """
    Reads the courses input file and converts it into Course objects.

    Each course block contains:
    - General course information
    - One or more program enrollment rows
    - Evaluation type
    """

    def parse(self, content: str) -> list[Course]:
        """
        Split the file into course blocks and parse each block separately.
        """
        blocks = content.split(SEPARATOR)
        courses: list[Course] = []

        for block in blocks:
            block = block.strip()

            # Skip the empty section before the first separator.
            if not block:
                continue

            courses.append(self._parse_block(block))

        return courses

    def _parse_block(self, block: str) -> Course:
        """
        Parse a single course block into a Course object.
        """
        # Remove empty lines and surrounding whitespace.
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

        # A valid block must contain at least:
        # name, number, instructor, one enrollment row, and evaluation type.
        if len(lines) < 4:
            raise ValueError(
                f"Malformed course block — expected at least 4 lines, "
                f"got {len(lines)}:\n{block}"
            )

        # Fixed fields at the top of the block.
        name = lines[0]
        course_number = lines[1]
        instructor = lines[2]

        if not course_number.isdigit() or len(course_number) != 5:
            raise ValueError(f"Invalid course number: '{course_number}'")

        # Last line defines how the course is evaluated.
        evaluation_type = lines[-1]

        if evaluation_type not in VALID_EVALUATION_TYPES:
            raise ValueError(f"Invalid evaluation type: '{evaluation_type}'")

        # All middle rows describe program enrollments.
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
        Parse one enrollment row into a ProgramEnrollment object.

        Expected format:
            <program_number>,<year>,<semester>,<status>
        """
        parts = [p.strip() for p in line.split(",")]

        if len(parts) != 4:
            raise ValueError(
                f"Malformed enrollment line — expected 4 comma-separated fields, "
                f"got {len(parts)}: '{line}'"
            )

        program_number, year_str, semester, status = parts

        # Program numbers are expected to contain exactly five digits.
        if not program_number.isdigit() or len(program_number) != 5:
            raise ValueError(f"Invalid program number: '{program_number}'")

        # Convert the academic year into an integer value.
        try:
            year = int(year_str)
        except ValueError:
            raise ValueError(
                f"Non-integer year in enrollment line: '{year_str}' (full line: '{line}')"
            )

        # Validate remaining enrollment fields.
        if year not in VALID_YEARS:
            raise ValueError(f"Invalid year: {year}")

        if semester not in VALID_SEMESTERS:
            raise ValueError(f"Invalid semester: '{semester}'")

        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: '{status}'")

        return ProgramEnrollment(
            program_number=program_number,
            year=year,
            semester=semester,
            status=status,
        )
