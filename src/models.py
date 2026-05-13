from dataclasses import dataclass, field
from datetime import date


# ---------------------------------------------------------------------------
# Data models
#
# These dataclasses are the "language" the rest of the system speaks.
# Every file reader transforms raw text into one of these structures,
# so that the scheduler never has to think about file formats at all.
# ---------------------------------------------------------------------------


@dataclass
class ProgramEnrollment:
    """
    Describes how a single course relates to one specific study program.

    A course can belong to multiple programs at different year levels,
    semesters, and with different obligation statuses — so a Course
    holds a list of these rather than a single flat set of fields.

    Example (from the courses file):
        83101,1,FALL,Obligatory
        → program_number="83101", year=1, semester="FALL", status="Obligatory"
    """

    program_number: str  # Identifies which study program this enrollment belongs to
    year: int            # Academic year within the program (e.g. 1st year, 2nd year)
    semester: str        # "FALL" or "SPRI" (spring) — when the course runs
    status: str          # "Obligatory" or "Elective" — how mandatory the course is


@dataclass
class Course:
    """
    Represents a single academic course and everything the scheduler needs to know about it.

    The `programs` list captures all the study programs that include this course,
    which is how the scheduler figures out which courses belong to a given exam period.
    The `evaluation_type` determines whether the course even needs an exam slot at all
    (a "Project" course typically doesn't sit a written exam).
    """

    name: str                        # Course title, e.g. "Physics 1"
    course_number: str               # Unique identifier, e.g. "83102"
    instructor: str                  # The person responsible for the course
    programs: list[ProgramEnrollment]  # Which programs include this course, and how
    evaluation_type: str             # "Exam" or "Project" — drives scheduling logic


@dataclass
class ExamPeriod:
    """
    Represents one exam window (a moed) within a semester.

    Each semester typically has two moedim (Aleph and Bet): Aleph is the
    first sitting, Bet is the resit for students who missed or failed Aleph.
    The scheduler uses `excluded_dates` to avoid placing exams on holidays,
    Shabbat, or any other blocked day within the period.

    Note on excluded_dates ranges: if the source file contains a date range
    (e.g. "- 02-03-2026, 04-03-2026 Purim"), both endpoints are stored as
    separate entries. The scheduler is responsible for treating everything
    between them as blocked if needed.
    """

    semester: str              # "FALL" or "SPRI" — which semester this period belongs to
    moed: str                  # "Aleph" (first sitting) or "Bet" (resit)
    start_date: date           # First day exams can be scheduled in this window
    end_date: date             # Last day exams can be scheduled in this window
    excluded_dates: list[date] = field(default_factory=list)  # Days that must stay empty