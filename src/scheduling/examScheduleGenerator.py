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
        # Use the default date handler unless another one was provided.
        self.date_handler = date_handler or ExamDateHandler()

        # Use the default conflict detector unless another one was provided.
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
        # Build the list of dates that can be used in this exam period.
        valid_dates = self.date_handler.get_valid_dates(exam_period)

        # Keep only courses that belong to the semester of this exam period.
        period_courses = self._courses_for_semester(courses, exam_period.semester)

        # If there is nothing to schedule, return an empty list.
        if not valid_dates or not period_courses:
            return []

        # This list will store every valid schedule that the recursion finds.
        schedules: list[ExamSchedule] = []

        # Start building schedules from the first course.
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
        # Collect schedules from all exam periods into one list.
        schedules: list[ExamSchedule] = []

        # Generate schedules separately for each period.
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
        # If all courses received dates, save this complete schedule.
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

        # Select the next course that needs an exam date.
        course = courses[course_index]

        # Try assigning the course to each valid date in the period.
        for exam_date in valid_dates:
            candidate_schedule = current_schedule + [
                ScheduledExam(course=course, exam_date=exam_date)
            ]

            # Continue only if the partial schedule is still valid.
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
        # This list will contain course copies for the requested semester only.
        period_courses: list[Course] = []

        for course in courses:
            # Keep only program rows that match the exam period semester.
            matching_programs = [
                program
                for program in course.programs
                if program.semester == semester
            ]

            # If the course is not taught in this semester, do not schedule it.
            if not matching_programs:
                continue

            # Create a course copy with only the relevant semester programs.
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
