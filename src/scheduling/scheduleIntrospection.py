"""Small helpers for reading and copying ExamSystem objects.

Several Part 4 services need to find a course inside a schedule. These helpers
keep that traversal in one place so snapshot, diff, and manual-move code do not
repeat the same loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


# A course can appear once in each exam period, such as Aleph and Bet.  The
# period is therefore part of the identity used by manual editing and diffs.
ExamInstanceKey = tuple[str, str, str]


@dataclass(frozen=True)
class ScheduledExamLocation:
    """One exam location inside an ExamSystem."""

    period_index: int
    exam_index: int
    semester: str
    moed: str
    exam: ScheduledExam

    @property
    def course_id(self) -> str:
        """Return the course id used by files and GUI controls."""
        return self.exam.course.course_number

    @property
    def course_name(self) -> str:
        """Return the readable course name."""
        return self.exam.course.name

    @property
    def exam_date(self) -> date:
        """Return the scheduled exam date."""
        return self.exam.exam_date

    @property
    def instance_key(self) -> ExamInstanceKey:
        """Return the stable course and period identity for this exam."""
        return (self.course_id, self.semester, self.moed)


def flatten_exam_system(exam_system: ExamSystem) -> list[ScheduledExamLocation]:
    """Return every scheduled exam with its position in the system."""
    locations: list[ScheduledExamLocation] = []

    for period_index, period_schedule in enumerate(exam_system.period_schedules):
        for exam_index, scheduled_exam in enumerate(period_schedule.scheduled_exams):
            locations.append(
                ScheduledExamLocation(
                    period_index=period_index,
                    exam_index=exam_index,
                    semester=period_schedule.semester,
                    moed=period_schedule.moed,
                    exam=scheduled_exam,
                )
            )

    return locations


def exam_instance_index(
    exam_system: ExamSystem,
) -> dict[ExamInstanceKey, ScheduledExamLocation]:
    """Map every course-period exam to its scheduled location.

    A course number alone is not unique when the same course has an Aleph and a
    Bet exam.  Including semester and moed prevents a diff or a manual move
    from silently selecting the wrong exam.
    """
    index: dict[ExamInstanceKey, ScheduledExamLocation] = {}
    for location in flatten_exam_system(exam_system):
        if location.instance_key in index:
            raise ValueError(
                "A course appears more than once in the same exam period: "
                f"{location.course_id} ({location.semester} {location.moed})."
            )
        index[location.instance_key] = location
    return index


def clone_exam_system_with_move(
    exam_system: ExamSystem,
    course_id: str,
    new_date: date,
    *,
    source_semester: str | None = None,
    source_moed: str | None = None,
    source_date: date | None = None,
) -> tuple[ExamSystem | None, date | None, str | None]:
    """Return a copied ExamSystem with one selected exam moved to a new date."""
    matches = [
        location
        for location in flatten_exam_system(exam_system)
        if location.course_id == course_id
    ]

    if source_semester is not None:
        matches = [
            location for location in matches if location.semester == source_semester
        ]
    if source_moed is not None:
        matches = [location for location in matches if location.moed == source_moed]
    if source_date is not None:
        matches = [location for location in matches if location.exam_date == source_date]

    if not matches:
        return None, None, f"Course {course_id} was not found in this schedule."

    if len(matches) > 1:
        return (
            None,
            None,
            f"Course {course_id} appears more than once. Choose a specific exam period.",
        )

    target = matches[0]
    new_period_schedules: list[ExamSchedule] = []

    for period_index, period_schedule in enumerate(exam_system.period_schedules):
        new_exams: list[ScheduledExam] = []

        for exam_index, scheduled_exam in enumerate(period_schedule.scheduled_exams):
            if period_index == target.period_index and exam_index == target.exam_index:
                new_exams.append(
                    ScheduledExam(
                        course=scheduled_exam.course,
                        exam_date=new_date,
                    )
                )
            else:
                new_exams.append(scheduled_exam)

        new_period_schedules.append(
            ExamSchedule(
                semester=period_schedule.semester,
                moed=period_schedule.moed,
                scheduled_exams=new_exams,
            )
        )

    return ExamSystem(period_schedules=new_period_schedules), target.exam_date, None
