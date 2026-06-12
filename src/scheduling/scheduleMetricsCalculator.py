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

    def calculate(
        self,
        exam_system: ExamSystem,
        schedule_id: int,
    ) -> ScheduleMetrics:
        """
        Return the five metric values for one exam system.

        schedule_id is the stable id of the schedule.
        """
        entries = self._flatten_exam_system(exam_system)

        # Calculate metrics that use exam pairs.
        mandatory_gaps = self._pair_gaps_by_program_year(
            entries,
            mandatory_only=True,
        )
        all_gaps = self._pair_gaps_by_program_year(
            entries,
            mandatory_only=False,
        )

        # Calculate metrics that use groups or dates.
        mandatory_spans = self._mandatory_spans(entries)
        exams_per_day = self._exam_counts_by_date(entries)

        return ScheduleMetrics(
            schedule_id=schedule_id,
            min_mandatory_gap=(
                min(mandatory_gaps)
                if mandatory_gaps
                else MISSING_METRIC_VALUE
            ),
            average_all_gap=(
                sum(all_gaps) / len(all_gaps)
                if all_gaps
                else MISSING_METRIC_VALUE
            ),
            elective_collision_count=self._elective_collision_count(entries),
            mandatory_span=(
                max(mandatory_spans)
                if mandatory_spans
                else MISSING_METRIC_VALUE
            ),
            max_exams_per_day=(
                max(exams_per_day.values())
                if exams_per_day
                else MISSING_METRIC_VALUE
            ),
        )

    def calculate_many(
        self,
        exam_systems: list[ExamSystem],
    ) -> list[ScheduleMetrics]:
        """Calculate metrics for many schedules."""
        return [
            self.calculate(
                exam_system,
                schedule_id=index,
            )
            for index, exam_system in enumerate(
                exam_systems,
                start=1,
            )
        ]

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

    @staticmethod
    def _all_program_year_keys(
        course: Course,
    ) -> set[ProgramYearKey]:
        """Return all program/year groups of a course."""
        return {
            (
                program.program_number,
                program.year,
            )
            for program in course.programs
        }

    @staticmethod
    def _mandatory_program_year_keys(
        course: Course,
    ) -> set[ProgramYearKey]:
        """Return program/year groups where the course is mandatory."""
        return {
            (
                program.program_number,
                program.year,
            )
            for program in course.programs
            if not _is_elective(program.status)
        }

    @staticmethod
    def _elective_program_numbers(
        course: Course,
    ) -> set[str]:
        """
        Return programs where the course is elective.

        If the same program is also mandatory, we keep it as mandatory.
        """
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

        return elective_programs.difference(mandatory_programs)


def _is_elective(status: str) -> bool:
    """Return True when the status is elective."""
    return status.strip().lower() == ELECTIVE_STATUS
