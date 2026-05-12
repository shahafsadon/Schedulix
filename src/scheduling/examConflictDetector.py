from dataclasses import dataclass
from datetime import date

from models import Course, ProgramEnrollment


ELECTIVE = "Elective"


@dataclass(frozen=True)
class ScheduledExam:
    """
    Represents one course after it was assigned to an exam date.

    This small model keeps conflict detection readable: instead of passing
    loose tuples around the code, each scheduled exam has a named course and
    a named date.
    """

    course: Course
    exam_date: date


@dataclass(frozen=True)
class ExamConflict:
    """
    Describes one critical conflict between two scheduled exams.

    A conflict is critical when both exams are on the same date, belong to the
    same program and study year, and are not both elective courses.
    """

    first_exam: ScheduledExam
    second_exam: ScheduledExam
    program_number: str
    year: int
    first_requirement: str
    second_requirement: str


class ExamConflictDetector:
    """
    Detects critical exam conflicts for version 1.0.

    Version 1.0 checks conflicts by date only. It does not check exam hours,
    repeated courses, rooms, or optimization preferences because those are not
    part of the current requirements.
    """

    def is_valid_schedule(self, scheduled_exams: list[ScheduledExam]) -> bool:
        """Return True when the schedule has no critical conflicts."""
        return not self.has_conflicts(scheduled_exams)

    def has_conflicts(self, scheduled_exams: list[ScheduledExam]) -> bool:
        """Return True when at least one critical conflict exists."""
        return bool(self.find_conflicts(scheduled_exams))

    def find_conflicts(
        self,
        scheduled_exams: list[ScheduledExam],
    ) -> list[ExamConflict]:
        """
        Return all critical conflicts found in the schedule.

        Each pair of exams is compared once. Exams on different dates cannot
        conflict in version 1.0, so they are skipped immediately.
        """
        conflicts: list[ExamConflict] = []

        for first_index, first_exam in enumerate(scheduled_exams):
            for second_exam in scheduled_exams[first_index + 1:]:
                if first_exam.exam_date != second_exam.exam_date:
                    continue

                conflict = self._find_conflict_for_same_date(
                    first_exam,
                    second_exam,
                )

                if conflict is not None:
                    conflicts.append(conflict)

        return conflicts

    def _find_conflict_for_same_date(
        self,
        first_exam: ScheduledExam,
        second_exam: ScheduledExam,
    ) -> ExamConflict | None:
        """
        Return a conflict if two same-date exams clash by program and year.

        Two elective courses are allowed to share a date. Every other
        combination is a critical conflict when program number and year match.
        """
        for first_program in first_exam.course.programs:
            for second_program in second_exam.course.programs:
                if not self._same_program_and_year(first_program, second_program):
                    continue

                if self._both_elective(first_program, second_program):
                    continue

                return ExamConflict(
                    first_exam=first_exam,
                    second_exam=second_exam,
                    program_number=first_program.program_number,
                    year=first_program.year,
                    first_requirement=first_program.status,
                    second_requirement=second_program.status,
                )

        return None

    @staticmethod
    def _same_program_and_year(
        first_program: ProgramEnrollment,
        second_program: ProgramEnrollment,
    ) -> bool:
        """Return True when two enrollment rows are for the same program year."""
        return (
            first_program.program_number == second_program.program_number
            and first_program.year == second_program.year
        )

    @staticmethod
    def _both_elective(
        first_program: ProgramEnrollment,
        second_program: ProgramEnrollment,
    ) -> bool:
        """Return True when both courses are elective for the compared program."""
        return first_program.status == ELECTIVE and second_program.status == ELECTIVE
