"""Presenter for uploaded-data visualization (SCRUM-119).

This presenter builds a display-ready snapshot of the data already parsed by
the upload workflow. It reads from the shared CacheManager when available, so
the preview reflects persisted application state, and can fall back to the
FileUploadService's local UploadedInputData snapshot for standalone tests.

No customTkinter imports live here. The screen renders the returned data, while
this presenter owns the summarizing and metadata-building logic.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.cache_manager import CacheManager
from gui.uploadService import UploadedInputData
from models import Course, ExamPeriod


@dataclass(frozen=True)
class CoursePreview:
    """One uploaded course row as shown in the input-data preview."""

    course_number: str
    name: str
    instructor: str
    evaluation_type: str
    enrollment_count: int
    program_numbers: list[str]


@dataclass(frozen=True)
class ExamPeriodPreview:
    """One uploaded exam period row as shown in the input-data preview."""

    semester: str
    moed: str
    start_date: str
    end_date: str
    day_count: int
    excluded_count: int


@dataclass(frozen=True)
class UploadedDataMetadata:
    """Compact metadata summary for the uploaded parsed data."""

    course_count: int
    program_count: int
    exam_period_count: int
    exam_course_count: int
    total_enrollment_count: int
    total_excluded_date_count: int
    evaluation_counts: dict[str, int]
    is_complete: bool


@dataclass(frozen=True)
class UploadedDataSnapshot:
    """Full display-ready snapshot returned to the upload screen."""

    courses: list[CoursePreview]
    programs: list[str]
    exam_periods: list[ExamPeriodPreview]
    metadata: UploadedDataMetadata


class UploadedDataPresenter:
    """Builds display-ready uploaded-data snapshots for the GUI."""

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        uploaded_data: UploadedInputData | None = None,
    ) -> None:
        """Create the presenter from cache and/or local upload state.

        Args:
            cache_manager: shared application cache. Preferred when supplied
                because later workflow screens read this same state.
            uploaded_data: local upload snapshot used when no cache exists.
        """
        self._cache = cache_manager
        self._uploaded_data = uploaded_data or UploadedInputData()

    def refresh(self) -> UploadedDataSnapshot:
        """Read the latest parsed data and return a display-ready snapshot."""
        courses, programs, exam_periods = self._load_current_data()

        course_rows = [self._course_preview(course) for course in courses]
        exam_period_rows = [
            self._exam_period_preview(exam_period)
            for exam_period in exam_periods
        ]

        return UploadedDataSnapshot(
            courses=course_rows,
            programs=programs,
            exam_periods=exam_period_rows,
            metadata=self._metadata(courses, programs, exam_periods),
        )

    def _load_current_data(
        self,
    ) -> tuple[list[Course], list[str], list[ExamPeriod]]:
        # Cache-backed state is the application source of truth after SCRUM-118.
        if self._cache is not None:
            return (
                list(self._cache.get_courses()),
                list(self._cache.get_selected_programs()),
                list(self._cache.get_exam_periods()),
            )

        return (
            list(self._uploaded_data.courses or []),
            list(self._uploaded_data.programs or []),
            list(self._uploaded_data.exam_periods or []),
        )

    @staticmethod
    def _course_preview(course: Course) -> CoursePreview:
        program_numbers = sorted(
            {enrollment.program_number for enrollment in course.programs}
        )
        return CoursePreview(
            course_number=course.course_number,
            name=course.name,
            instructor=course.instructor,
            evaluation_type=course.evaluation_type,
            enrollment_count=len(course.programs),
            program_numbers=program_numbers,
        )

    @staticmethod
    def _exam_period_preview(exam_period: ExamPeriod) -> ExamPeriodPreview:
        day_count = (exam_period.end_date - exam_period.start_date).days + 1
        return ExamPeriodPreview(
            semester=exam_period.semester,
            moed=exam_period.moed,
            start_date=exam_period.start_date.strftime("%d-%m-%Y"),
            end_date=exam_period.end_date.strftime("%d-%m-%Y"),
            day_count=day_count,
            excluded_count=len(exam_period.excluded_dates),
        )

    @staticmethod
    def _metadata(
        courses: list[Course],
        programs: list[str],
        exam_periods: list[ExamPeriod],
    ) -> UploadedDataMetadata:
        evaluation_counts: dict[str, int] = {}
        total_enrollments = 0

        for course in courses:
            evaluation_counts[course.evaluation_type] = (
                evaluation_counts.get(course.evaluation_type, 0) + 1
            )
            total_enrollments += len(course.programs)

        total_excluded_dates = sum(
            len(exam_period.excluded_dates)
            for exam_period in exam_periods
        )

        return UploadedDataMetadata(
            course_count=len(courses),
            program_count=len(programs),
            exam_period_count=len(exam_periods),
            exam_course_count=evaluation_counts.get("Exam", 0),
            total_enrollment_count=total_enrollments,
            total_excluded_date_count=total_excluded_dates,
            evaluation_counts=evaluation_counts,
            is_complete=bool(courses and programs and exam_periods),
        )
