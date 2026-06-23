from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


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
        """Return the course identifier used by files and commands."""
        return self.exam.course.course_number

    @property
    def course_name(self) -> str:
        """Return the readable course name."""
        return self.exam.course.name

    @property
    def exam_date(self) -> date:
        """Return the scheduled exam date."""
        return self.exam.exam_date


def flatten_exam_system(exam_system: ExamSystem) -> list[ScheduledExamLocation]:
    """Return every scheduled exam with its exact position in the system."""
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


def course_date_index(exam_system: ExamSystem) -> dict[str, ScheduledExamLocation]:
    """Map each course id to its scheduled exam location."""
    index: dict[str, ScheduledExamLocation] = {}

    for location in flatten_exam_system(exam_system):
        index[location.course_id] = location

    return index


def clone_exam_system_with_move(
    exam_system: ExamSystem,
    course_id: str,
    new_date: date,
) -> tuple[ExamSystem | None, date | None, str | None]:
    """Return a copied ExamSystem with one course moved to a new date."""
    matches = [
        location
        for location in flatten_exam_system(exam_system)
        if location.course_id == course_id
    ]

    if not matches:
        return None, None, f"Course {course_id} was not found in this schedule."

    if len(matches) > 1:
        return None, None, f"Course {course_id} appears more than once."

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
