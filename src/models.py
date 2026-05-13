from dataclasses import dataclass, field
from datetime import date


@dataclass
class ProgramEnrollment:
    """
    Represents the way a course appears in one study program.

    The same course can appear in several programs, sometimes in different
    years, semesters, or requirement types. For that reason, Course keeps a
    list of ProgramEnrollment objects instead of storing these fields directly.
    """

    program_number: str  # Study program number, for example "83101"
    year: int            # Academic year in that program
    semester: str        # Semester code from the input file, such as "FALL" or "SPRI"
    status: str          # Course requirement type, such as "Obligatory" or "Elective"


@dataclass
class Course:
    """
    Represents one course after it was parsed from the courses input file.

    This model keeps the course details together with the list of programs
    that include it. The scheduling logic later uses evaluation_type to decide
    whether the course should receive an exam date.
    """

    name: str                        # Course name as it appears in the input file
    course_number: str               # Unique course identifier
    instructor: str                  # Course instructor name
    programs: list[ProgramEnrollment]  # Program-specific details for this course
    evaluation_type: str             # Evaluation method, for example "Exam" or "Project"


@dataclass
class ExamPeriod:
    """
    Represents one exam period for a specific semester and moed.

    start_date and end_date define the allowed scheduling window. excluded_dates
    contains dates that must not be used, such as holidays or other blocked days.
    """

    semester: str              # Semester code, for example "FALL" or "SPRI"
    moed: str                  # Exam moed, for example "Aleph" or "Bet"
    start_date: date           # First date that can be used for exams
    end_date: date             # Last date that can be used for exams
    excluded_dates: list[date] = field(default_factory=list)  # Blocked dates inside the period