from datetime import date

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ProgramEnrollment
from ranking_settings import ScheduleMetrics
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


def make_course(
    course_number: str,
    *,
    name: str | None = None,
    program: str = "83101",
    year: int = 1,
    status: str = "Obligatory",
) -> Course:
    return Course(
        name=name or f"Course {course_number}",
        course_number=course_number,
        instructor="Dr. Test",
        programs=[ProgramEnrollment(program, year, "FALL", status)],
        evaluation_type="Exam",
    )


def make_exam(
    course_number: str,
    exam_date: date,
    *,
    name: str | None = None,
    program: str = "83101",
    year: int = 1,
    status: str = "Obligatory",
) -> ScheduledExam:
    return ScheduledExam(
        course=make_course(
            course_number,
            name=name,
            program=program,
            year=year,
            status=status,
        ),
        exam_date=exam_date,
    )


def make_system(*exams: ScheduledExam) -> ExamSystem:
    return ExamSystem(
        period_schedules=[
            ExamSchedule(
                semester="FALL",
                moed="Aleph",
                scheduled_exams=list(exams),
            )
        ]
    )


def make_metrics(schedule_id: int = 1) -> ScheduleMetrics:
    return ScheduleMetrics(
        schedule_id=schedule_id,
        min_mandatory_gap=7,
        average_all_gap=8.0,
        elective_collision_count=0,
        mandatory_span=10,
        max_exams_per_day=1,
    )


def max_exams_settings(k: int) -> SchedulingConstraintSettings:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = (
        ThresholdConstraintSetting(enabled=True, k=k)
    )
    return settings
