"""Presenter for the program-details view (SCRUM-123).

This presenter builds a structured, read-only view of one selected study
program: its course list grouped by year and semester, each course's
requirement type (Obligatory/Elective) and evaluation method (Exam/Project/
Attendance). Like every presenter in the MVP design, it holds no customTkinter
code and is fully unit-testable without a GUI.

The data model (see models.py) has no dedicated "program name" field: a program
is identified only by its number, and its attributes live on the
ProgramEnrollment rows attached to each Course. This presenter therefore
reconstructs the per-program picture by scanning every course's enrollments.
"""
from __future__ import annotations

from dataclasses import dataclass

from models import Course

# Stable display order for semesters and requirement grouping. Unknown values
# are pushed to the end so unexpected input never crashes the view.
SEMESTER_ORDER = {"FALL": 0, "SPRI": 1, "SUMM": 2}


@dataclass(frozen=True)
class CourseDetail:
    """One course as shown inside a program, for a specific enrollment row.

    A course can appear in several (year, semester) slots of the same program,
    so the same course_number may produce more than one CourseDetail.
    """

    course_number: str
    name: str
    instructor: str
    status: str            # "Obligatory" or "Elective"
    evaluation_type: str   # "Exam", "Project", or "Attendance"


@dataclass(frozen=True)
class SemesterGroup:
    """All courses of a program for one (year, semester) slot."""

    year: int
    semester: str
    courses: list[CourseDetail]


@dataclass(frozen=True)
class ProgramDetails:
    """Full read-only picture of one study program.

    `groups` is ordered by year, then by semester, so the view can render it
    top-to-bottom without sorting again.
    """

    program_number: str
    course_count: int
    groups: list[SemesterGroup]


class ProgramDetailsPresenter:
    """Builds per-program detail views from the loaded courses."""

    def __init__(self, courses: list[Course]) -> None:
        # Keep the loaded courses; details are computed on demand per program.
        self._courses = courses

    def get_details(self, program_number: str) -> ProgramDetails:
        """Return the grouped detail view for a single program.

        Scans every course's enrollments, keeps only the rows that belong to
        the requested program, and groups the resulting courses by (year,
        semester). The same course is listed once per matching enrollment row.
        """
        # Collect one CourseDetail per enrollment row that matches the program.
        # Keyed by (year, semester) so courses fall into the right slot.
        grouped: dict[tuple[int, str], list[CourseDetail]] = {}
        total = 0

        for course in self._courses:
            for enrollment in course.programs:
                if enrollment.program_number != program_number:
                    continue

                detail = CourseDetail(
                    course_number=course.course_number,
                    name=course.name,
                    instructor=course.instructor,
                    status=enrollment.status,
                    evaluation_type=course.evaluation_type,
                )
                grouped.setdefault((enrollment.year, enrollment.semester), []).append(
                    detail
                )
                total += 1

        # Turn the dict into an ordered list of SemesterGroup objects.
        groups: list[SemesterGroup] = []
        for (year, semester) in sorted(grouped, key=self._group_sort_key):
            courses = sorted(
                grouped[(year, semester)],
                key=lambda detail: detail.course_number,
            )
            groups.append(
                SemesterGroup(year=year, semester=semester, courses=courses)
            )

        return ProgramDetails(
            program_number=program_number,
            course_count=total,
            groups=groups,
        )

    @staticmethod
    def _group_sort_key(key: tuple[int, str]) -> tuple[int, int, str]:
        """Sort groups by year, then by semester in requirement order."""
        year, semester = key
        return (year, SEMESTER_ORDER.get(semester, len(SEMESTER_ORDER)), semester)