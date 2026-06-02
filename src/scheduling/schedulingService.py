"""Scheduling service that connects the GUI cache to the Version 1.0 engine
(SCRUM-125).

Version 1.0 exposes its full pipeline through SchedulixApp.run(), which reads
input files from disk, generates schedules, and writes an output file. The
Version 2.0 GUI already holds its data in memory (inside the CacheManager) and
must not re-read files or write an output file just to display results on
screen.

This service bridges that gap. It takes the data already stored in the cache
(courses, exam periods, selected programs), runs the same core Version 1.0 logic
(course filtering + exam-system generation) without any file I/O, stores the
resulting schedules back into the cache, and returns them to the caller.

It deliberately reuses the existing CourseFilter and ExamScheduleGenerator
rather than duplicating any scheduling logic, so the Version 2.0 results stay
identical to Version 1.0 for the same inputs.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.cache_manager import CacheManager
from scheduling.courseFilter import CourseFilter
from scheduling.examScheduleGenerator import ExamScheduleGenerator, ExamSystem


@dataclass(frozen=True)
class SchedulingOutcome:
    """Summary of one scheduling run, returned to the presenter.

    `schedules` is also stored in the cache as a side effect; it is returned
    here too so the caller can react without a second cache read. The counts
    let the UI show a short status line without recomputing anything.
    """

    relevant_course_count: int
    schedule_count: int
    schedules: list[ExamSystem]


class SchedulingService:
    """Runs the Version 1.0 scheduling core on data held in the cache.

    The service is stateless apart from its injected collaborators. All input
    comes from the CacheManager passed to run(), and all output goes back into
    that same cache, keeping the GUI's single source of truth consistent.
    """

    def __init__(
        self,
        course_filter: CourseFilter | None = None,
        schedule_generator: ExamScheduleGenerator | None = None,
    ) -> None:
        """Create the service with its scheduling collaborators.

        Args:
            course_filter: reuses the Version 1.0 filter; a default is created
                when none is supplied so application code stays simple.
            schedule_generator: reuses the Version 1.0 generator; defaulted the
                same way. Both are injectable so tests can substitute fakes.
        """
        # Reuse the real Version 1.0 components unless tests inject their own.
        self._course_filter = course_filter or CourseFilter()
        self._schedule_generator = schedule_generator or ExamScheduleGenerator()

    def run(self, cache: CacheManager) -> SchedulingOutcome:
        """Generate exam systems from the cached data and store them back.

        Reads courses, exam periods and selected programs from the cache, keeps
        only the Exam courses belonging to the selected programs, generates all
        valid exam systems, writes them back into the cache, and returns a
        summary.

        Raises:
            ValueError: if the cache is missing courses, exam periods, or a
                program selection — i.e. the user reached generation without
                completing the earlier wizard steps.
        """
        courses = cache.get_courses()
        exam_periods = cache.get_exam_periods()
        selected_programs = cache.get_selected_programs()

        # Fail clearly rather than silently producing an empty result: each of
        # these is set by an earlier wizard step, so an empty value means the
        # user (or a bug) skipped a required step.
        if not courses:
            raise ValueError("No courses loaded. Load a courses file first.")
        if not exam_periods:
            raise ValueError("No exam periods loaded. Load a dates file first.")
        if not selected_programs:
            raise ValueError("No programs selected. Select at least one program.")

        # Step 1: keep only Exam courses that belong to the selected programs.
        # This is the exact same filtering rule used by Version 1.0.
        relevant_courses = self._course_filter.filter_relevant_courses(
            courses,
            selected_programs,
        )

        # Step 2: generate every valid exam-system option (no file I/O here).
        schedules = self._schedule_generator.generate_exam_systems(
            relevant_courses,
            exam_periods,
        )

        # Step 3: store the results in the cache so the output screen (and a
        # later restart) can read them without regenerating.
        cache.set_generated_schedules(schedules)

        return SchedulingOutcome(
            relevant_course_count=len(relevant_courses),
            schedule_count=len(schedules),
            schedules=schedules,
        )