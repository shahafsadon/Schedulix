from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import combinations

from models import Course
from ranking_settings import MISSING_METRIC_VALUE, ScheduleMetrics
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSystem


ProgramYearKey = tuple[str, int]
MandatorySpanKey = tuple[str, int, str, str]

ELECTIVE_STATUS = "elective"


@dataclass(frozen=True)
class _ExamEntry:
    """One exam with its semester and moed."""

    exam: ScheduledExam
    semester: str
    moed: str


class ScheduleMetricsCalculator:
    """
    Calculates the five ranking metrics for one ExamSystem.

    This class does not create schedules. It only measures schedules that were
    already created.
    """

    def __init__(self) -> None:
        """Create small caches for course-level metric groups.

        The same Course objects appear in thousands of generated schedules.
        Their program/year groups do not change during one run, so caching them
        avoids repeating the same string checks for every candidate schedule.
        """
        self._all_program_year_cache: dict[int, set[ProgramYearKey]] = {}
        self._mandatory_program_year_cache: dict[int, set[ProgramYearKey]] = {}
        self._elective_program_cache: dict[int, set[str]] = {}

    def calculate(
        self,
        exam_system: ExamSystem,
        schedule_id: int,
    ) -> ScheduleMetrics:
        """
        Return the five metric values for one exam system.

        schedule_id is the stable id of the schedule.
        """
        # Build all small indexes in one pass. This avoids repeating the same
        # course/status work for every metric and every generated schedule.
        all_dates_by_group: dict[ProgramYearKey, list[date]] = defaultdict(list)
        mandatory_dates_by_group: dict[ProgramYearKey, list[date]] = defaultdict(list)
        mandatory_dates_by_period: dict[MandatorySpanKey, list[date]] = defaultdict(list)
        exams_per_day: dict[date, int] = defaultdict(int)
        exams_by_date: dict[date, list[ScheduledExam]] = defaultdict(list)

        for period_schedule in exam_system.period_schedules:
            semester = period_schedule.semester
            moed = period_schedule.moed

            for exam in period_schedule.scheduled_exams:
                exam_date = exam.exam_date
                course = exam.course

                for key in self._all_program_year_keys(course):
                    all_dates_by_group[key].append(exam_date)

                for program_number, year in self._mandatory_program_year_keys(course):
                    mandatory_dates_by_group[(program_number, year)].append(exam_date)
                    mandatory_dates_by_period[
                        (
                            program_number,
                            year,
                            semester,
                            moed,
                        )
                    ].append(exam_date)

                exams_per_day[exam_date] += 1
                exams_by_date[exam_date].append(exam)

        min_mandatory_gap = self._minimum_pair_gap(mandatory_dates_by_group)
        average_all_gap = self._average_pair_gap(all_dates_by_group)
        mandatory_span = self._maximum_span(mandatory_dates_by_period)

        return ScheduleMetrics(
            schedule_id=schedule_id,
            min_mandatory_gap=min_mandatory_gap,
            average_all_gap=average_all_gap,
            elective_collision_count=self._elective_collision_count_by_exam_date(
                exams_by_date
            ),
            mandatory_span=mandatory_span,
            max_exams_per_day=(
                max(exams_per_day.values())
                if exams_per_day
                else MISSING_METRIC_VALUE
            ),
        )

    def calculate_many(
        self,
        exam_systems: list[ExamSystem],
        starting_schedule_id: int = 1,
    ) -> list[ScheduleMetrics]:
        """Calculate metrics for many schedules.

        ``starting_schedule_id`` keeps IDs stable when callers calculate
        metrics batch-by-batch during progressive generation.  The default
        preserves the original full-list behavior.
        """
        return [
            self.calculate(
                exam_system,
                schedule_id=index,
            )
            for index, exam_system in enumerate(
                exam_systems,
                start=starting_schedule_id,
            )
        ]

    @staticmethod
    def _minimum_pair_gap(
        dates_by_group: dict[ProgramYearKey, list[date]],
    ) -> int | float:
        """Return the smallest gap across all groups."""
        minimum_gap: int | None = None
        for dates in dates_by_group.values():
            for first_date, second_date in combinations(dates, 2):
                gap = abs((second_date - first_date).days)
                if minimum_gap is None or gap < minimum_gap:
                    minimum_gap = gap

        return minimum_gap if minimum_gap is not None else MISSING_METRIC_VALUE

    @staticmethod
    def _average_pair_gap(
        dates_by_group: dict[ProgramYearKey, list[date]],
    ) -> float:
        """Return the average gap across all same-program/year pairs."""
        total_gap = 0
        pair_count = 0
        for dates in dates_by_group.values():
            for first_date, second_date in combinations(dates, 2):
                total_gap += abs((second_date - first_date).days)
                pair_count += 1

        if pair_count == 0:
            return MISSING_METRIC_VALUE
        return total_gap / pair_count

    @staticmethod
    def _maximum_span(
        dates_by_group: dict[MandatorySpanKey, list[date]],
    ) -> int | float:
        """Return the largest first-to-last mandatory exam span."""
        maximum_span: int | None = None
        for dates in dates_by_group.values():
            if len(dates) < 2:
                continue
            span = (max(dates) - min(dates)).days
            if maximum_span is None or span > maximum_span:
                maximum_span = span

        return maximum_span if maximum_span is not None else MISSING_METRIC_VALUE

    @staticmethod
    def _flatten_exam_system(
        exam_system: ExamSystem,
    ) -> list[_ExamEntry]:
        """Return all exams as one simple list."""
        entries: list[_ExamEntry] = []

        for period_schedule in exam_system.period_schedules:
            for exam in period_schedule.scheduled_exams:
                entries.append(
                    _ExamEntry(
                        exam=exam,
                        semester=period_schedule.semester,
                        moed=period_schedule.moed,
                    )
                )

        return entries

    def _pair_gaps_by_program_year(
        self,
        entries: list[_ExamEntry],
        mandatory_only: bool,
    ) -> list[int]:
        """Return day gaps for exam pairs in each program/year."""
        dates_by_group: dict[
            ProgramYearKey,
            list[date],
        ] = defaultdict(list)

        for entry in entries:
            if mandatory_only:
                keys = self._mandatory_program_year_keys(entry.exam.course)
            else:
                keys = self._all_program_year_keys(entry.exam.course)

            # A multi-program course is counted in each matching group.
            for key in keys:
                dates_by_group[key].append(entry.exam.exam_date)

        gaps: list[int] = []
        for dates in dates_by_group.values():
            for first_date, second_date in combinations(dates, 2):
                gaps.append(abs((second_date - first_date).days))

        return gaps

    def _mandatory_spans(
        self,
        entries: list[_ExamEntry],
    ) -> list[int]:
        """Return span days for mandatory exam groups."""
        dates_by_group: dict[
            MandatorySpanKey,
            list[date],
        ] = defaultdict(list)

        for entry in entries:
            for program_number, year in self._mandatory_program_year_keys(
                entry.exam.course
            ):
                key = (
                    program_number,
                    year,
                    entry.semester,
                    entry.moed,
                )
                dates_by_group[key].append(entry.exam.exam_date)

        spans: list[int] = []
        for dates in dates_by_group.values():
            if len(dates) < 2:
                continue

            spans.append((max(dates) - min(dates)).days)

        return spans

    @staticmethod
    def _exam_counts_by_date(
        entries: list[_ExamEntry],
    ) -> dict[date, int]:
        """Count exams per date."""
        counts: dict[date, int] = defaultdict(int)

        for entry in entries:
            counts[entry.exam.exam_date] += 1

        return counts

    def _elective_collision_count(
        self,
        entries: list[_ExamEntry],
    ) -> int:
        """Count elective pairs on the same date and program."""
        entries_by_date: dict[
            date,
            list[_ExamEntry],
        ] = defaultdict(list)

        for entry in entries:
            entries_by_date[entry.exam.exam_date].append(entry)

        collision_count = 0

        for same_day_entries in entries_by_date.values():
            for first_entry, second_entry in combinations(same_day_entries, 2):
                first_programs = self._elective_program_numbers(
                    first_entry.exam.course
                )
                second_programs = self._elective_program_numbers(
                    second_entry.exam.course
                )

                collision_count += len(
                    first_programs.intersection(second_programs)
                )

        return collision_count

    def _elective_collision_count_by_date(
        self,
        entries_by_date: dict[date, list[_ExamEntry]],
    ) -> int:
        """Count elective same-day pairs from an existing date index."""
        collision_count = 0

        for same_day_entries in entries_by_date.values():
            for first_entry, second_entry in combinations(same_day_entries, 2):
                first_programs = self._elective_program_numbers(
                    first_entry.exam.course
                )
                second_programs = self._elective_program_numbers(
                    second_entry.exam.course
                )

                collision_count += len(
                    first_programs.intersection(second_programs)
                )

        return collision_count

    def _elective_collision_count_by_exam_date(
        self,
        exams_by_date: dict[date, list[ScheduledExam]],
    ) -> int:
        """Count elective same-day pairs from an existing exam-date index."""
        collision_count = 0

        for same_day_exams in exams_by_date.values():
            for first_exam, second_exam in combinations(same_day_exams, 2):
                first_programs = self._elective_program_numbers(first_exam.course)
                second_programs = self._elective_program_numbers(second_exam.course)
                collision_count += len(
                    first_programs.intersection(second_programs)
                )

        return collision_count

    def _all_program_year_keys(
        self,
        course: Course,
    ) -> set[ProgramYearKey]:
        """Return all program/year groups of a course."""
        cache_key = id(course)
        cached = self._all_program_year_cache.get(cache_key)
        if cached is None:
            cached = {
                (
                    program.program_number,
                    program.year,
                )
                for program in course.programs
            }
            self._all_program_year_cache[cache_key] = cached
        return cached

    def _mandatory_program_year_keys(
        self,
        course: Course,
    ) -> set[ProgramYearKey]:
        """Return program/year groups where the course is mandatory."""
        cache_key = id(course)
        cached = self._mandatory_program_year_cache.get(cache_key)
        if cached is None:
            cached = {
                (
                    program.program_number,
                    program.year,
                )
                for program in course.programs
                if not _is_elective(program.status)
            }
            self._mandatory_program_year_cache[cache_key] = cached
        return cached

    def _elective_program_numbers(
        self,
        course: Course,
    ) -> set[str]:
        """
        Return programs where the course is elective.

        If the same program is also mandatory, we keep it as mandatory.
        """
        cache_key = id(course)
        cached = self._elective_program_cache.get(cache_key)
        if cached is None:
            mandatory_programs = {
                program.program_number
                for program in course.programs
                if not _is_elective(program.status)
            }

            elective_programs = {
                program.program_number
                for program in course.programs
                if _is_elective(program.status)
            }

            cached = elective_programs.difference(mandatory_programs)
            self._elective_program_cache[cache_key] = cached
        return cached


def _is_elective(status: str) -> bool:
    """Return True when the status is elective."""
    return status.strip().lower() == ELECTIVE_STATUS
