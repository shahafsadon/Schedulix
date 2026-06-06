from fileReader.baseFileReader import BaseFileReader
from models import Course, ProgramEnrollment


SEPARATOR = "$$$$"

VALID_YEARS = {
    1,
    2,
    3,
    4,
}

VALID_SEMESTERS = {
    "FALL",
    "SPRI",
    "SUMM",
}

VALID_STATUSES = {
    "Obligatory",
    "Elective",
}

VALID_EVALUATION_TYPES = {
    "Exam",
    "Project",
    "Attendance",
}


class CoursesFileReader(BaseFileReader[list[Course]]):
    """Parses course records from the required format."""

    def parse(
        self,
        content: str,
    ) -> list[Course]:
        if not content.strip():
            raise ValueError(
                "Courses file is empty."
            )

        if not content.lstrip().startswith(SEPARATOR):
            raise ValueError(
                "Courses file must start each record with '$$$$'."
            )

        courses: list[Course] = []
        seen_course_numbers: set[str] = set()

        for block in content.split(SEPARATOR):
            if not block.strip():
                continue

            course = self._parse_block(block)

            if course.course_number in seen_course_numbers:
                raise ValueError(
                    f"Duplicate course number: '{course.course_number}'"
                )

            seen_course_numbers.add(
                course.course_number
            )

            courses.append(course)

        if not courses:
            raise ValueError(
                "Courses file does not contain any course records."
            )

        return courses

    def _parse_block(
        self,
        block: str,
    ) -> Course:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if len(lines) < 5:
            raise ValueError(
                "Malformed course block - expected name, number, "
                "instructor, at least one enrollment, and evaluation "
                f"type:\n{block}"
            )

        name = lines[0]
        course_number = lines[1]
        instructor = lines[2]
        evaluation_type = lines[-1]

        if not course_number.isdigit() or len(course_number) != 5:
            raise ValueError(
                f"Invalid course number: '{course_number}'"
            )

        if evaluation_type not in VALID_EVALUATION_TYPES:
            raise ValueError(
                f"Invalid evaluation type: '{evaluation_type}'"
            )

        programs = [
            self._parse_enrollment(line)
            for line in lines[3:-1]
        ]

        keys = [
            self._enrollment_key(program)
            for program in programs
        ]

        if len(keys) != len(set(keys)):
            raise ValueError(
                f"Course '{course_number}' contains "
                "a duplicate enrollment row."
            )

        return Course(
            name=name,
            course_number=course_number,
            instructor=instructor,
            programs=programs,
            evaluation_type=evaluation_type,
        )

    @staticmethod
    def _parse_enrollment(
        line: str,
    ) -> ProgramEnrollment:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 4:
            raise ValueError(
                "Malformed enrollment line - expected 4 "
                f"comma-separated fields, got {len(parts)}: '{line}'"
            )

        program_number = parts[0]
        year_text = parts[1]
        semester = parts[2]
        status = parts[3]

        if not program_number.isdigit() or len(program_number) != 5:
            raise ValueError(
                f"Invalid program number: '{program_number}'"
            )

        try:
            year = int(year_text)
        except ValueError as error:
            raise ValueError(
                f"Non-integer year: '{year_text}'"
            ) from error

        if year not in VALID_YEARS:
            raise ValueError(
                f"Invalid year: {year}"
            )

        if semester not in VALID_SEMESTERS:
            raise ValueError(
                f"Invalid semester: '{semester}'"
            )

        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status: '{status}'"
            )

        return ProgramEnrollment(
            program_number=program_number,
            year=year,
            semester=semester,
            status=status,
        )

    @staticmethod
    def _enrollment_key(
        program: ProgramEnrollment,
    ) -> tuple[str, int, str, str]:
        return (
            program.program_number,
            program.year,
            program.semester,
            program.status,
        )