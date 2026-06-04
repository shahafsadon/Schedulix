from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from models import Course, ProgramEnrollment


ELECTIVE = "elective"
ResourceKey = tuple[str, int]


@dataclass(frozen=True)
class ScheduledExam:
    """Represents one course exam assigned to one calendar date."""

    course: Course
    exam_date: date


@dataclass(frozen=True)
class ExamConflict:
    """Describes one critical Version 1.0 conflict between two exams."""

    first_exam: ScheduledExam
    second_exam: ScheduledExam
    program_number: str
    year: int
    first_requirement: str
    second_requirement: str


class ExamConflictDetector:
    """
    Detects Version 1.0 exam conflicts.

    Two exams conflict when they are scheduled on the same date and share a
    study-program/year resource, unless both courses are elective for that
    resource.

    has_conflicts() is optimized for the common boolean question. It scans the
    exams once and stops as soon as a conflict is found. find_conflicts() keeps
    the pair-based implementation because callers requesting a report need the
    concrete conflicting pairs.
    """

    def is_valid_schedule(
        self,
        scheduled_exams: list[ScheduledExam],
    ) -> bool:
        """Return True when the schedule contains no critical conflicts."""
        return not self.has_conflicts(scheduled_exams)

    def has_conflicts(
        self,
        scheduled_exams: list[ScheduledExam],
    ) -> bool:
        """Return True immediately after the first critical conflict is found."""
        occupancy: dict[
            date,
            dict[ResourceKey, list[int]],
        ] = {}

        for exam in scheduled_exams:
            day_usage = occupancy.setdefault(
                exam.exam_date,
                {},
            )

            obligatory_keys, elective_keys = self._resource_keys(
                exam.course
            )

            # An obligatory exam conflicts with every exam already occupying
            # the same program/year resource on this date.
            for key in obligatory_keys:
                usage = day_usage.get(key)

                if usage is not None and usage[0] > 0:
                    return True

            # An elective exam conflicts only with a previously scheduled
            # obligatory exam on the same resource and date.
            for key in elective_keys:
                usage = day_usage.get(key)

                if usage is not None and usage[1] > 0:
                    return True

            for key in obligatory_keys:
                usage = day_usage.setdefault(
                    key,
                    [0, 0],
                )

                usage[0] += 1
                usage[1] += 1

            for key in elective_keys:
                usage = day_usage.setdefault(
                    key,
                    [0, 0],
                )

                usage[0] += 1

        return False

    def find_conflicts(
        self,
        scheduled_exams: list[ScheduledExam],
    ) -> list[ExamConflict]:
        """Return all concrete conflict pairs in the supplied schedule."""
        conflicts: list[ExamConflict] = []

        for first_index, first_exam in enumerate(
            scheduled_exams
        ):
            for second_exam in scheduled_exams[first_index + 1:]:
                if (
                    first_exam.exam_date
                    != second_exam.exam_date
                ):
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
        """Return one reason why two same-date exams conflict, if one exists."""
        for first_program in first_exam.course.programs:
            for second_program in second_exam.course.programs:
                if not self._same_program_and_year(
                    first_program,
                    second_program,
                ):
                    continue

                if self._both_elective(
                    first_program,
                    second_program,
                ):
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
    def _resource_keys(
        course: Course,
    ) -> tuple[
        set[ResourceKey],
        set[ResourceKey],
    ]:
        """Return obligatory and elective program/year resources for a course."""
        obligatory = {
            (
                program.program_number,
                program.year,
            )
            for program in course.programs
            if program.status.strip().lower() != ELECTIVE
        }

        elective = {
            (
                program.program_number,
                program.year,
            )
            for program in course.programs
            if program.status.strip().lower() == ELECTIVE
        }

        # A contradictory duplicated enrollment is treated as obligatory.
        # This is safer than allowing an invalid same-day assignment.
        elective.difference_update(obligatory)

        return obligatory, elective

    @staticmethod
    def _same_program_and_year(
        first_program: ProgramEnrollment,
        second_program: ProgramEnrollment,
    ) -> bool:
        return (
            first_program.program_number
            == second_program.program_number
            and first_program.year
            == second_program.year
        )

    @staticmethod
    def _both_elective(
        first_program: ProgramEnrollment,
        second_program: ProgramEnrollment,
    ) -> bool:
        return (
            first_program.status.strip().lower()
            == ELECTIVE
            and second_program.status.strip().lower()
            == ELECTIVE
        )