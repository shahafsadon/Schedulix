from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from itertools import product

from constraint_settings import SchedulingConstraintSettings
from models import Course, ExamPeriod
from scheduling.constraints import (
    ConstraintEvaluationContext,
    ConstraintRegistry,
)
from scheduling.examConflictDetector import (
    ExamConflictDetector,
    ScheduledExam,
)
from scheduling.examDateHandler import ExamDateHandler


ResourceKey = tuple[str, int]

# The first value is the total number of exams using a resource.
# The second value is the number of obligatory exams using that resource.
Usage = list[int]


@dataclass(frozen=True)
class ExamSchedule:
    """Represents one valid schedule option for one semester/moed period."""

    semester: str
    moed: str
    scheduled_exams: list[ScheduledExam]


@dataclass(frozen=True)
class ExamSystem:
    """Represents one complete exam-system option across relevant periods."""

    period_schedules: list[ExamSchedule]


@dataclass(frozen=True)
class _CourseProfile:
    """Precomputed conflict resources used while placing one course."""

    course: Course
    obligatory_keys: frozenset[ResourceKey]
    elective_keys: frozenset[ResourceKey]


class ExamScheduleGenerator:
    """
    Generates valid exam schedules efficiently.

    The old implementation repeatedly scanned previously placed exams and
    precomputed an O(course_count^2) collision graph.

    This implementation keeps an occupancy map indexed by date and
    (program, year), so testing one candidate placement depends on the
    candidate course resources rather than the size of the partial schedule.

    Complete exam systems are exposed both as a compatibility list method and
    as a lazy iterator. File output should consume iter_exam_systems() so the
    program does not retain every Cartesian-product result in memory.
    """

    def __init__(
        self,
        date_handler: ExamDateHandler | None = None,
        conflict_detector: ExamConflictDetector | None = None,
        constraint_registry: ConstraintRegistry | None = None,
        constraint_settings: SchedulingConstraintSettings | None = None,
    ) -> None:
        self.date_handler = (
            date_handler
            or ExamDateHandler()
        )

        # Kept as a public collaborator for compatibility with the existing
        # project design and tests. The optimized recursion below performs
        # incremental occupancy checks directly.
        self.conflict_detector = (
            conflict_detector
            or ExamConflictDetector()
        )

        self.constraint_registry = (
            constraint_registry
            or ConstraintRegistry.default(
                constraint_settings
            )
        )

    def generate_for_period(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> list[ExamSchedule]:
        """Return every valid schedule for one exam period."""
        return list(
            self.iter_for_period(
                courses,
                exam_period,
            )
        )

    def iter_for_period(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> Iterator[ExamSchedule]:
        """Yield valid schedules for one period without storing them first."""
        valid_dates = (
            self.date_handler.get_valid_dates(
                exam_period
            )
        )

        period_courses = (
            self._courses_for_semester(
                courses,
                exam_period.semester,
            )
        )

        if (
            not valid_dates
            or not period_courses
        ):
            return

        self._ensure_unique_course_numbers(
            period_courses
        )

        # Place constrained courses first so impossible branches fail earlier.
        # This changes search order, but not the set of results.
        profiles = sorted(
            (
                self._profile(course)
                for course in period_courses
            ),
            key=self._profile_weight,
            reverse=True,
        )

        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ] = {}

        course_numbers_by_date: dict[
            date,
            set[str],
        ] = {}

        current_schedule: list[
            ScheduledExam
        ] = []

        yield from self._iter_period_schedules(
            profiles=profiles,
            valid_dates=valid_dates,
            course_index=0,
            current_schedule=current_schedule,
            occupancy=occupancy,
            course_numbers_by_date=course_numbers_by_date,
            exam_period=exam_period,
        )

    def generate_for_periods(
        self,
        courses: list[Course],
        exam_periods: list[ExamPeriod],
    ) -> list[ExamSchedule]:
        """Return a flat list of valid schedules for all supplied periods."""
        schedules: list[
            ExamSchedule
        ] = []

        for exam_period in exam_periods:
            schedules.extend(
                self.iter_for_period(
                    courses,
                    exam_period,
                )
            )

        return schedules

    def generate_exam_systems(
        self,
        courses: list[Course],
        exam_periods: list[ExamPeriod],
    ) -> list[ExamSystem]:
        """
        Compatibility wrapper for callers that explicitly need a list.

        The file-output application flow should use iter_exam_systems().
        """
        return list(
            self.iter_exam_systems(
                courses,
                exam_periods,
            )
        )

    def iter_exam_systems(
        self,
        courses: list[Course],
        exam_periods: list[ExamPeriod],
    ) -> Iterator[ExamSystem]:
        """
        Yield complete exam systems lazily.

        Period-specific options are reused while combining periods. Complete
        systems are not accumulated in memory.

        When usable date sets are pairwise disjoint, cross-period conflicts are
        impossible under the Version 1.0 same-date rule. In that common case,
        a lazy Cartesian product is sufficient.
        """
        relevant_periods = [
            exam_period
            for exam_period in exam_periods
            if self._courses_for_semester(
                courses,
                exam_period.semester,
            )
        ]

        if not relevant_periods:
            return

        # With one relevant period there is no Cartesian combination. Stream
        # each option immediately instead of retaining the entire period list.
        if len(relevant_periods) == 1:
            for schedule in self.iter_for_period(
                courses,
                relevant_periods[0],
            ):
                exam_system = ExamSystem(
                    period_schedules=[
                        schedule
                    ]
                )

                if self._is_valid_complete_system(
                    exam_system
                ):
                    yield exam_system

            return

        period_options: list[
            list[ExamSchedule]
        ] = []

        period_date_sets: list[
            set[date]
        ] = []

        for exam_period in relevant_periods:
            schedules = list(
                self.iter_for_period(
                    courses,
                    exam_period,
                )
            )

            if not schedules:
                return

            period_options.append(
                schedules
            )

            period_date_sets.append(
                set(
                    self.date_handler.get_valid_dates(
                        exam_period
                    )
                )
            )

        if self._date_sets_are_pairwise_disjoint(
            period_date_sets
        ):
            for combination in product(
                *period_options
            ):
                exam_system = ExamSystem(
                    period_schedules=list(
                        combination
                    )
                )

                if self._is_valid_complete_system(
                    exam_system
                ):
                    yield exam_system

            return

        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ] = {}

        course_numbers_by_date: dict[
            date,
            set[str],
        ] = {}

        current_periods: list[
            ExamSchedule
        ] = []

        profile_cache: dict[
            int,
            _CourseProfile,
        ] = {}

        yield from self._iter_exam_systems(
            period_options=period_options,
            period_index=0,
            current_periods=current_periods,
            occupancy=occupancy,
            course_numbers_by_date=course_numbers_by_date,
            profile_cache=profile_cache,
        )

    def _iter_period_schedules(
        self,
        profiles: list[_CourseProfile],
        valid_dates: list[date],
        course_index: int,
        current_schedule: list[ScheduledExam],
        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ],
        course_numbers_by_date: dict[
            date,
            set[str],
        ],
        exam_period: ExamPeriod,
    ) -> Iterator[ExamSchedule]:
        """Recursively yield valid options for one exam period."""
        if course_index == len(
            profiles
        ):
            yield ExamSchedule(
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

            return

        profile = profiles[
            course_index
        ]

        for exam_date in valid_dates:
            if not self._can_place(
                profile=profile,
                exam_date=exam_date,
                current_schedule=current_schedule,
                occupancy=occupancy,
                course_numbers_by_date=course_numbers_by_date,
                semester=exam_period.semester,
                moed=exam_period.moed,
            ):
                continue

            self._place(
                profile,
                exam_date,
                occupancy,
                course_numbers_by_date,
            )

            current_schedule.append(
                ScheduledExam(
                    course=profile.course,
                    exam_date=exam_date,
                )
            )

            yield from self._iter_period_schedules(
                profiles=profiles,
                valid_dates=valid_dates,
                course_index=(
                    course_index + 1
                ),
                current_schedule=current_schedule,
                occupancy=occupancy,
                course_numbers_by_date=course_numbers_by_date,
                exam_period=exam_period,
            )

            current_schedule.pop()

            self._remove(
                profile,
                exam_date,
                occupancy,
                course_numbers_by_date,
            )

    def _iter_exam_systems(
        self,
        period_options: list[
            list[ExamSchedule]
        ],
        period_index: int,
        current_periods: list[
            ExamSchedule
        ],
        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ],
        course_numbers_by_date: dict[
            date,
            set[str],
        ],
        profile_cache: dict[
            int,
            _CourseProfile,
        ],
    ) -> Iterator[ExamSystem]:
        """Combine overlapping periods and reject invalid branches early."""
        if period_index == len(
            period_options
        ):
            exam_system = ExamSystem(
                period_schedules=list(
                    current_periods
                )
            )

            if self._is_valid_complete_system(
                exam_system
            ):
                yield exam_system

            return

        for option in period_options[
            period_index
        ]:
            placed: list[
                tuple[
                    _CourseProfile,
                    date,
                ]
            ] = []

            for exam in option.scheduled_exams:
                course_id = id(
                    exam.course
                )

                profile = (
                    profile_cache.get(
                        course_id
                    )
                )

                if profile is None:
                    profile = self._profile(
                        exam.course
                    )

                    profile_cache[
                        course_id
                    ] = profile

                if not self._can_place(
                    profile=profile,
                    exam_date=exam.exam_date,
                    current_schedule=self._flatten_period_schedules(
                        current_periods
                    )
                    + [
                        ScheduledExam(
                            course=placed_profile.course,
                            exam_date=placed_date,
                        )
                        for placed_profile, placed_date in placed
                    ],
                    occupancy=occupancy,
                    course_numbers_by_date=course_numbers_by_date,
                    semester=option.semester,
                    moed=option.moed,
                ):
                    break

                self._place(
                    profile,
                    exam.exam_date,
                    occupancy,
                    course_numbers_by_date,
                )

                placed.append(
                    (
                        profile,
                        exam.exam_date,
                    )
                )

            else:
                current_periods.append(
                    option
                )

                yield from self._iter_exam_systems(
                    period_options=period_options,
                    period_index=(
                        period_index + 1
                    ),
                    current_periods=current_periods,
                    occupancy=occupancy,
                    course_numbers_by_date=course_numbers_by_date,
                    profile_cache=profile_cache,
                )

                current_periods.pop()

            for (
                profile,
                exam_date,
            ) in reversed(placed):
                self._remove(
                    profile,
                    exam_date,
                    occupancy,
                    course_numbers_by_date,
                )

    def _is_valid_complete_system(
        self,
        exam_system: ExamSystem,
    ) -> bool:
        """Return True when all enabled final-system constraints accept it."""
        result = self.constraint_registry.evaluate_final(
            ConstraintEvaluationContext(
                exam_system=exam_system,
            )
        )

        return result.accepted

    @staticmethod
    def _flatten_period_schedules(
        period_schedules: list[ExamSchedule],
    ) -> list[ScheduledExam]:
        """Return the already selected period exams as one list."""
        scheduled_exams: list[ScheduledExam] = []

        for period_schedule in period_schedules:
            scheduled_exams.extend(
                period_schedule.scheduled_exams
            )

        return scheduled_exams

    def _can_place(
        self,
        profile: _CourseProfile,
        exam_date: date,
        current_schedule: list[ScheduledExam],
        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ],
        course_numbers_by_date: dict[
            date,
            set[str],
        ],
        semester: str | None,
        moed: str | None,
    ) -> bool:
        """Return True when all enabled constraints accept the candidate."""
        result = self.constraint_registry.evaluate_incremental(
            ConstraintEvaluationContext(
                candidate_exam=profile.course,
                candidate_date=exam_date,
                partial_schedule=current_schedule,
                semester=semester,
                moed=moed,
                metadata={
                    "occupancy": occupancy,
                    "course_numbers_by_date": course_numbers_by_date,
                },
            )
        )

        return result.accepted

    @staticmethod
    def _place(
        profile: _CourseProfile,
        exam_date: date,
        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ],
        course_numbers_by_date: dict[
            date,
            set[str],
        ],
    ) -> None:
        """Record one temporary recursive placement."""
        day_usage = occupancy.setdefault(
            exam_date,
            {},
        )

        course_numbers_by_date.setdefault(
            exam_date,
            set(),
        ).add(
            profile.course.course_number
        )

        for key in profile.obligatory_keys:
            usage = day_usage.setdefault(
                key,
                [0, 0],
            )

            usage[0] += 1
            usage[1] += 1

        for key in profile.elective_keys:
            usage = day_usage.setdefault(
                key,
                [0, 0],
            )

            usage[0] += 1

    @staticmethod
    def _remove(
        profile: _CourseProfile,
        exam_date: date,
        occupancy: dict[
            date,
            dict[ResourceKey, Usage],
        ],
        course_numbers_by_date: dict[
            date,
            set[str],
        ],
    ) -> None:
        """Undo one temporary recursive placement."""
        day_usage = occupancy[
            exam_date
        ]

        for key in profile.obligatory_keys:
            usage = day_usage[
                key
            ]

            usage[0] -= 1
            usage[1] -= 1

            if usage == [0, 0]:
                del day_usage[
                    key
                ]

        for key in profile.elective_keys:
            usage = day_usage[
                key
            ]

            usage[0] -= 1

            if usage == [0, 0]:
                del day_usage[
                    key
                ]

        course_numbers = (
            course_numbers_by_date[
                exam_date
            ]
        )

        course_numbers.remove(
            profile.course.course_number
        )

        if not course_numbers:
            del course_numbers_by_date[
                exam_date
            ]

        if not day_usage:
            del occupancy[
                exam_date
            ]

    @staticmethod
    def _profile(
        course: Course,
    ) -> _CourseProfile:
        """Precompute program/year conflict resources for one course."""
        obligatory_keys = {
            (
                program.program_number,
                program.year,
            )
            for program in course.programs
            if (
                program.status.strip().lower()
                != "elective"
            )
        }

        elective_keys = {
            (
                program.program_number,
                program.year,
            )
            for program in course.programs
            if (
                program.status.strip().lower()
                == "elective"
            )
        }

        # A contradictory duplicate row is treated as obligatory.
        elective_keys.difference_update(
            obligatory_keys
        )

        return _CourseProfile(
            course=course,
            obligatory_keys=frozenset(
                obligatory_keys
            ),
            elective_keys=frozenset(
                elective_keys
            ),
        )

    @staticmethod
    def _profile_weight(
        profile: _CourseProfile,
    ) -> tuple[int, int]:
        """Place courses with more conflict resources earlier in the search."""
        return (
            (
                2
                * len(
                    profile.obligatory_keys
                )
                + len(
                    profile.elective_keys
                )
            ),
            len(
                profile.obligatory_keys
            ),
        )

    @staticmethod
    def _date_sets_are_pairwise_disjoint(
        date_sets: list[
            set[date]
        ],
    ) -> bool:
        """Return True when no usable date belongs to two exam periods."""
        seen: set[
            date
        ] = set()

        for date_set in date_sets:
            if seen.intersection(
                date_set
            ):
                return False

            seen.update(
                date_set
            )

        return True

    @staticmethod
    def _ensure_unique_course_numbers(
        courses: list[Course],
    ) -> None:
        """Reject duplicated course IDs before recursion creates bad output."""
        seen: set[
            str
        ] = set()

        for course in courses:
            if course.course_number in seen:
                raise ValueError(
                    "Duplicate course number in scheduling input: "
                    f"'{course.course_number}'"
                )

            seen.add(
                course.course_number
            )

    @staticmethod
    def _courses_for_semester(
        courses: list[Course],
        semester: str,
    ) -> list[Course]:
        """Return course copies containing only rows for one semester."""
        period_courses: list[
            Course
        ] = []

        for course in courses:
            matching_programs = [
                program
                for program in course.programs
                if (
                    program.semester
                    == semester
                )
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