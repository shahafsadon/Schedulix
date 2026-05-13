from dataclasses import dataclass
from datetime import date

from models import Course, ExamPeriod
from scheduling.examConflictDetector import ExamConflictDetector, ScheduledExam
from scheduling.examDateHandler import ExamDateHandler


@dataclass(frozen=True)
class ExamSchedule:
    """
    Represents one valid schedule option for a single exam period.

    semester and moed identify the exam period this schedule belongs to.
    scheduled_exams contains the courses with their assigned exam dates.
    """

    semester: str
    moed: str
    scheduled_exams: list[ScheduledExam]


class ExamScheduleGenerator:
    """
    Generates all valid exam schedule options for exam periods.

    The generator assigns each relevant course to one possible date in the
    matching exam period. While building a schedule, it uses the conflict
    detector to keep only combinations without critical conflicts.
    """

    def __init__(
        self,
        date_handler: ExamDateHandler | None = None,
        conflict_detector: ExamConflictDetector | None = None,
    ) -> None:
        """
        Create a schedule generator with its helper services.

        Parameters are optional so tests can provide custom helpers if needed,
        while regular application code can use the default project classes.
        """
        self.date_handler = date_handler or ExamDateHandler()
        self.conflict_detector = conflict_detector or ExamConflictDetector()

    def generate_for_period(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> list[ExamSchedule]:
        """
        Generate every valid schedule option for one exam period.

        Only courses that belong to the period semester are considered. If the
        period has no valid dates or no matching courses, no schedules are
        returned.
        """
        valid_dates = self.date_handler.get_valid_dates(exam_period)
        period_courses = self._courses_for_semester(courses, exam_period.semester)

        if not valid_dates or not period_courses:
            return []

        schedules: list[ExamSchedule] = []
        self._build_schedules(
            courses=period_courses,
            valid_dates=valid_dates,
            course_index=0,
            current_schedule=[],
            exam_period=exam_period,
            schedules=schedules,
        )
        return schedules

    def generate_for_periods(
        self,
        courses: list[Course],
        exam_periods: list[ExamPeriod],
    ) -> list[ExamSchedule]:
        """
        Generate valid schedule options for each given exam period.

        The result is a flat list. Each ExamSchedule still stores its semester
        and moed, so the output layer can group the schedules later.
        """
        schedules: list[ExamSchedule] = []

        for exam_period in exam_periods:
            schedules.extend(self.generate_for_period(courses, exam_period))

        return schedules

    def _build_schedules(
        self,
        courses: list[Course],
        valid_dates: list[date],
        course_index: int,
        current_schedule: list[ScheduledExam],
        exam_period: ExamPeriod,
        schedules: list[ExamSchedule],
    ) -> None:
        """
        Recursively assign dates to courses and collect valid schedules.

        A partial schedule is checked immediately after adding each exam. This
        avoids continuing with combinations that already contain a conflict.
        """
        if course_index == len(courses):
            schedules.append(
                ExamSchedule(
                    semester=exam_period.semester,
                    moed=exam_period.moed,
                    scheduled_exams=sorted(
                        current_schedule,
                        key=lambda exam: (
                            exam.exam_date,
                            exam.course.course_number,
                        ),
                    ),
                )
            )
            return

        course = courses[course_index]

        for exam_date in valid_dates:
            candidate_schedule = current_schedule + [
                ScheduledExam(course=course, exam_date=exam_date)
            ]

            if self.conflict_detector.is_valid_schedule(candidate_schedule):
                self._build_schedules(
                    courses=courses,
                    valid_dates=valid_dates,
                    course_index=course_index + 1,
                    current_schedule=candidate_schedule,
                    exam_period=exam_period,
                    schedules=schedules,
                )

    @staticmethod
    def _courses_for_semester(courses: list[Course], semester: str) -> list[Course]:
        """
        Keep only courses that have at least one program row in the semester.

        The returned Course objects include only the matching program rows, so
        conflict checks are based on the same semester being scheduled.
        """
        period_courses: list[Course] = []

        for course in courses:
            matching_programs = [
                program
                for program in course.programs
                if program.semester == semester
            ]

            if not matching_programs:
                continue

            period_courses.append(
                Course(
                    name=course.name,
                    course_number=course.course_number,
                    instructor=course.instructor,
                    programs=matching_programs,
                    evaluation_type=course.evaluation_type,
                )
            )

        return period_courses
