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
DateIndex = dict[ResourceKey, list[date]]
PeriodDateIndex = dict[tuple[str, int, str | None, str | None], list[date]]
ElectiveCountIndex = dict[date, dict[str, int]]
CollisionIndex = dict[str, int]
ExamCountIndex = dict[date, int]


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


@dataclass
class SchedulingDiagnostics:
    """Diagnostic counters for recursive candidate evaluation."""

    generated_candidates: int = 0
    accepted_candidates: int = 0
    pruned_candidates: int = 0


@dataclass(frozen=True)
class _CourseProfile:
    """Precomputed conflict resources used while placing one course."""

    course: Course
    obligatory_keys: frozenset[ResourceKey]
    elective_keys: frozenset[ResourceKey]
    all_keys: frozenset[ResourceKey]
    elective_programs: frozenset[str]


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

    Academic-review orientation
    ---------------------------
    This class is the scheduling-domain producer used by Version 34's
    progressive flow.  The important architectural point is that it answers
    only one question: "which ``ExamSystem`` objects are valid under the active
    constraints?"  It does not rank schedules and does not know about GUI
    previews.  Ranking and Top-N retention are handled later by
    ``ScheduleRankingService`` and ``RankedResultsBuffer``.

    Algorithmic idea
    ----------------
    The generator uses recursive backtracking with incremental constraint
    checks.  For each candidate exam/date placement, it updates compact indexes
    such as occupancy by date and program/year.  These indexes let constraints
    reject invalid branches early instead of generating every combination and
    filtering afterward.
    """

    def __init__(
        self,
        date_handler: ExamDateHandler | None = None,
        conflict_detector: ExamConflictDetector | None = None,
        constraint_registry: ConstraintRegistry | None = None,
        constraint_settings: SchedulingConstraintSettings | None = None,
    ) -> None:
        """Create a generator with injectable helpers and active constraints.

        Parameters
        ----------
        date_handler:
            Builds valid date lists for exam periods.
        conflict_detector:
            Kept for compatibility and final conflict checks.
        constraint_registry:
            Optional explicit registry, mainly useful for tests.
        constraint_settings:
            Version 34 settings used to build the default registry.

        Side effects
        ------------
        Initializes ``diagnostics`` counters used by higher-level callers to
        explain generated/accepted/pruned candidate counts.
        """
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

        self.diagnostics = SchedulingDiagnostics()

    def reset_diagnostics(self) -> None:
        """Reset recursive candidate-evaluation counters."""
        self.diagnostics = SchedulingDiagnostics()

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
        """Yield valid schedules for one period without storing them first.

        The method is lazy: it yields each valid ``ExamSchedule`` as soon as the
        recursive search completes that option.  This behavior is essential for
        Version 34 because progressive generation can consume schedules without
        materializing a full list.
        """
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
            # No valid dates or no courses for the semester means there is no
            # period schedule to yield.  Returning early avoids entering the
            # recursive search with impossible input.
            return

        self._ensure_unique_course_numbers(
            period_courses
        )

        # Place constrained courses first so impossible branches fail earlier.
        # This changes search order, but not the set of results.
        # The profile weight approximates how many program/year resources a
        # course touches.  More constrained courses are better pruning anchors.
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

        mandatory_dates_by_key: DateIndex = {}
        all_dates_by_key: DateIndex = {}
        mandatory_period_dates_by_key: PeriodDateIndex = {}
        elective_counts_by_date_program: ElectiveCountIndex = {}
        elective_collisions_by_program: CollisionIndex = {}
        exam_counts_by_date: ExamCountIndex = {}

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
            mandatory_dates_by_key=mandatory_dates_by_key,
            all_dates_by_key=all_dates_by_key,
            mandatory_period_dates_by_key=mandatory_period_dates_by_key,
            elective_counts_by_date_program=elective_counts_by_date_program,
            elective_collisions_by_program=elective_collisions_by_program,
            exam_counts_by_date=exam_counts_by_date,
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

        Version 34 relevance
        --------------------
        ``SchedulingService.run_progressive()`` consumes this iterator directly
        and batches the yielded systems.  The generator therefore remains
        responsible only for validity, while ranking/preview logic stays outside
        this class.
        """
        # Ignore periods that have no relevant courses.  This keeps the
        # Cartesian combination smaller and avoids creating empty period
        # schedules that would not change the final exam system.
        relevant_periods = [
            exam_period
            for exam_period in exam_periods
            if self._courses_for_semester(
                courses,
                exam_period.semester,
            )
        ]

        if not relevant_periods:
            # Nothing schedulable exists for the selected courses/periods.
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
                    # Final-system evaluation is still applied because Version
                    # 34 constraints may include rules that cannot be proven
                    # during a single candidate placement.
                    yield exam_system

            return

        period_options: list[
            list[ExamSchedule]
        ] = []

        period_date_sets: list[
            set[date]
        ] = []

        for exam_period in relevant_periods:
            # Period options are still materialized per period for the
            # multi-period Cartesian product.  Complete exam systems, however,
            # are yielded lazily instead of accumulated in one large list.
            schedules = list(
                self.iter_for_period(
                    courses,
                    exam_period,
                )
            )

            if not schedules:
                # If one relevant period has no valid options, no complete exam
                # system can exist.
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
            # Fast path: disjoint date sets cannot create same-date conflicts
            # across periods, so a lazy Cartesian product is enough.
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

        mandatory_dates_by_key: DateIndex = {}
        all_dates_by_key: DateIndex = {}
        mandatory_period_dates_by_key: PeriodDateIndex = {}
        elective_counts_by_date_program: ElectiveCountIndex = {}
        elective_collisions_by_program: CollisionIndex = {}
        exam_counts_by_date: ExamCountIndex = {}

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
            mandatory_dates_by_key=mandatory_dates_by_key,
            all_dates_by_key=all_dates_by_key,
            mandatory_period_dates_by_key=mandatory_period_dates_by_key,
            elective_counts_by_date_program=elective_counts_by_date_program,
            elective_collisions_by_program=elective_collisions_by_program,
            exam_counts_by_date=exam_counts_by_date,
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
        mandatory_dates_by_key: DateIndex,
        all_dates_by_key: DateIndex,
        mandatory_period_dates_by_key: PeriodDateIndex,
        elective_counts_by_date_program: ElectiveCountIndex,
        elective_collisions_by_program: CollisionIndex,
        exam_counts_by_date: ExamCountIndex,
        exam_period: ExamPeriod,
    ) -> Iterator[ExamSchedule]:
        """Recursively yield valid options for one exam period."""
        if course_index == len(
            profiles
        ):
            # Base case: every course in the period has been placed.  Sorting
            # keeps output deterministic regardless of recursive placement
            # order.
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
            # Try one candidate date for the current course.  The registry is
            # consulted before mutating state so invalid branches are pruned
            # before deeper recursion.
            if not self._can_place(
                profile=profile,
                exam_date=exam_date,
                current_schedule=current_schedule,
                occupancy=occupancy,
                course_numbers_by_date=course_numbers_by_date,
                mandatory_dates_by_key=mandatory_dates_by_key,
                all_dates_by_key=all_dates_by_key,
                mandatory_period_dates_by_key=mandatory_period_dates_by_key,
                elective_counts_by_date_program=elective_counts_by_date_program,
                elective_collisions_by_program=elective_collisions_by_program,
                exam_counts_by_date=exam_counts_by_date,
                semester=exam_period.semester,
                moed=exam_period.moed,
            ):
                continue

            # Place the candidate into all incremental indexes, recurse, then
            # remove it.  This is the standard backtracking pattern: mutate,
            # explore, undo.
            self._place(
                profile,
                exam_date,
                occupancy,
                course_numbers_by_date,
                mandatory_dates_by_key,
                all_dates_by_key,
                mandatory_period_dates_by_key,
                elective_counts_by_date_program,
                elective_collisions_by_program,
                exam_counts_by_date,
                exam_period.semester,
                exam_period.moed,
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
                mandatory_dates_by_key=mandatory_dates_by_key,
                all_dates_by_key=all_dates_by_key,
                mandatory_period_dates_by_key=mandatory_period_dates_by_key,
                elective_counts_by_date_program=elective_counts_by_date_program,
                elective_collisions_by_program=elective_collisions_by_program,
                exam_counts_by_date=exam_counts_by_date,
                exam_period=exam_period,
            )

            current_schedule.pop()

            # The remove call must mirror _place exactly.  If the indexes were
            # not restored, later branches would be evaluated against stale
            # schedule state.
            self._remove(
                profile,
                exam_date,
                occupancy,
                course_numbers_by_date,
                mandatory_dates_by_key,
                all_dates_by_key,
                mandatory_period_dates_by_key,
                elective_counts_by_date_program,
                elective_collisions_by_program,
                exam_counts_by_date,
                exam_period.semester,
                exam_period.moed,
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
        mandatory_dates_by_key: DateIndex,
        all_dates_by_key: DateIndex,
        mandatory_period_dates_by_key: PeriodDateIndex,
        elective_counts_by_date_program: ElectiveCountIndex,
        elective_collisions_by_program: CollisionIndex,
        exam_counts_by_date: ExamCountIndex,
        profile_cache: dict[
            int,
            _CourseProfile,
        ],
    ) -> Iterator[ExamSystem]:
        """Combine overlapping periods and reject invalid branches early."""
        if period_index == len(
            period_options
        ):
            # Base case: one option has been chosen for every relevant period.
            # The completed ExamSystem may still need final-system constraint
            # checks before it is yielded.
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
            # ``placed`` records all temporary placements made for this period
            # option so they can be rolled back if the option is rejected or
            # after recursion returns.
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
                    # Profiles are immutable resource summaries.  Caching them
                    # avoids recomputing program/year keys for the same Course
                    # object while combining period options.
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
                    mandatory_dates_by_key=mandatory_dates_by_key,
                    all_dates_by_key=all_dates_by_key,
                    mandatory_period_dates_by_key=mandatory_period_dates_by_key,
                    elective_counts_by_date_program=elective_counts_by_date_program,
                    elective_collisions_by_program=elective_collisions_by_program,
                    exam_counts_by_date=exam_counts_by_date,
                    semester=option.semester,
                    moed=option.moed,
                ):
                    # The current period option conflicts with already selected
                    # period options.  Break out and roll back anything placed
                    # from this option.
                    break

                self._place(
                    profile,
                    exam.exam_date,
                    occupancy,
                    course_numbers_by_date,
                    mandatory_dates_by_key,
                    all_dates_by_key,
                    mandatory_period_dates_by_key,
                    elective_counts_by_date_program,
                    elective_collisions_by_program,
                    exam_counts_by_date,
                    option.semester,
                    option.moed,
                )

                placed.append(
                    (
                        profile,
                        exam.exam_date,
                    )
                )

            else:
                # The for-loop did not break, so this period option is
                # compatible with all previous choices.  Recurse to choose an
                # option for the next period.
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
                    mandatory_dates_by_key=mandatory_dates_by_key,
                    all_dates_by_key=all_dates_by_key,
                    mandatory_period_dates_by_key=mandatory_period_dates_by_key,
                    elective_counts_by_date_program=elective_counts_by_date_program,
                    elective_collisions_by_program=elective_collisions_by_program,
                    exam_counts_by_date=exam_counts_by_date,
                    profile_cache=profile_cache,
                )

                current_periods.pop()

            for (
                profile,
                exam_date,
            ) in reversed(placed):
                # Roll back in reverse placement order to restore indexes to
                # exactly the state they had before this option was tried.
                self._remove(
                    profile,
                    exam_date,
                    occupancy,
                    course_numbers_by_date,
                    mandatory_dates_by_key,
                    all_dates_by_key,
                    mandatory_period_dates_by_key,
                    elective_counts_by_date_program,
                    elective_collisions_by_program,
                    exam_counts_by_date,
                    option.semester,
                    option.moed,
                )

    def _is_valid_complete_system(
        self,
        exam_system: ExamSystem,
    ) -> bool:
        """Return True when all enabled final-system constraints accept it."""
        if not self.constraint_registry.requires_final_system_evaluation():
            # Avoid building/evaluating a final context when all enabled
            # constraints have already been enforced incrementally.
            return True

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
        mandatory_dates_by_key: DateIndex,
        all_dates_by_key: DateIndex,
        mandatory_period_dates_by_key: PeriodDateIndex,
        elective_counts_by_date_program: ElectiveCountIndex,
        elective_collisions_by_program: CollisionIndex,
        exam_counts_by_date: ExamCountIndex,
        semester: str | None,
        moed: str | None,
    ) -> bool:
        """Return True when all enabled constraints accept the candidate.

        This is the central pruning gate in the backtracking algorithm.  Every
        candidate placement passes through the active ``ConstraintRegistry``.
        Accepted/rejected counters are recorded so Version 34 callers can
        explain how much work was pruned.
        """
        self.diagnostics.generated_candidates += 1

        # The metadata dictionary provides constraints with fast indexes built
        # by _place/_remove.  This avoids repeatedly scanning the whole partial
        # schedule for common checks such as same-date occupancy or gap rules.
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
                    "candidate_obligatory_keys": profile.obligatory_keys,
                    "candidate_all_keys": profile.all_keys,
                    "candidate_elective_programs": profile.elective_programs,
                    "mandatory_dates_by_key": mandatory_dates_by_key,
                    "all_dates_by_key": all_dates_by_key,
                    "mandatory_period_dates_by_key": mandatory_period_dates_by_key,
                    "elective_counts_by_date_program": elective_counts_by_date_program,
                    "elective_collisions_by_program": elective_collisions_by_program,
                    "exam_counts_by_date": exam_counts_by_date,
                },
            )
        )

        if result.accepted:
            # "accepted candidates" are candidate placements accepted by
            # incremental constraints, not necessarily complete schedules.
            self.diagnostics.accepted_candidates += 1
        else:
            # "pruned candidates" are branches avoided before deeper recursion.
            self.diagnostics.pruned_candidates += 1

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
        mandatory_dates_by_key: DateIndex,
        all_dates_by_key: DateIndex,
        mandatory_period_dates_by_key: PeriodDateIndex,
        elective_counts_by_date_program: ElectiveCountIndex,
        elective_collisions_by_program: CollisionIndex,
        exam_counts_by_date: ExamCountIndex,
        semester: str | None,
        moed: str | None,
    ) -> None:
        """Record one temporary recursive placement.

        The method updates every incremental index that constraints may need.
        These updates are temporary: the matching ``_remove`` call must reverse
        them after the recursive branch is explored.
        """
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

        exam_counts_by_date[exam_date] = exam_counts_by_date.get(exam_date, 0) + 1

        # Gap/span constraints need to know prior dates by program/year.  The
        # indexes are updated at placement time so _can_place can evaluate the
        # next candidate cheaply.
        for key in profile.obligatory_keys:
            mandatory_dates_by_key.setdefault(key, []).append(exam_date)
            mandatory_period_dates_by_key.setdefault(
                (key[0], key[1], semester, moed),
                [],
            ).append(exam_date)

        for key in profile.all_keys:
            all_dates_by_key.setdefault(key, []).append(exam_date)

        date_elective_counts = elective_counts_by_date_program.setdefault(exam_date, {})
        for program_number in profile.elective_programs:
            # Adding one elective exam creates one new elective collision with
            # each existing elective exam for the same program on that date.
            existing_count = date_elective_counts.get(program_number, 0)
            elective_collisions_by_program[program_number] = (
                elective_collisions_by_program.get(program_number, 0)
                + existing_count
            )
            date_elective_counts[program_number] = existing_count + 1

        for key in profile.obligatory_keys:
            # Usage format is [total exams, obligatory exams].  It lets the
            # same-date conflict rule distinguish mandatory/elective cases.
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
        mandatory_dates_by_key: DateIndex,
        all_dates_by_key: DateIndex,
        mandatory_period_dates_by_key: PeriodDateIndex,
        elective_counts_by_date_program: ElectiveCountIndex,
        elective_collisions_by_program: CollisionIndex,
        exam_counts_by_date: ExamCountIndex,
        semester: str | None,
        moed: str | None,
    ) -> None:
        """Undo one temporary recursive placement.

        This method is the exact inverse of ``_place``.  Backtracking depends on
        this symmetry: after a branch is explored, all indexes must return to
        their previous state before the next candidate date/option is tried.
        """
        day_usage = occupancy[
            exam_date
        ]

        exam_count = exam_counts_by_date[exam_date] - 1
        if exam_count == 0:
            del exam_counts_by_date[exam_date]
        else:
            exam_counts_by_date[exam_date] = exam_count

        for key in profile.obligatory_keys:
            _remove_one_date(mandatory_dates_by_key, key, exam_date)
            _remove_one_date(
                mandatory_period_dates_by_key,
                (key[0], key[1], semester, moed),
                exam_date,
            )

        for key in profile.all_keys:
            _remove_one_date(all_dates_by_key, key, exam_date)

        date_elective_counts = elective_counts_by_date_program.get(exam_date, {})
        for program_number in profile.elective_programs:
            # Removing one elective exam removes the collisions it created with
            # the remaining electives for the same program/date.
            current_count = date_elective_counts[program_number]
            remaining_count = current_count - 1
            new_collision_count = (
                elective_collisions_by_program.get(program_number, 0)
                - remaining_count
            )
            if new_collision_count == 0:
                elective_collisions_by_program.pop(program_number, None)
            else:
                elective_collisions_by_program[program_number] = new_collision_count

            if remaining_count == 0:
                del date_elective_counts[program_number]
            else:
                date_elective_counts[program_number] = remaining_count

        if not date_elective_counts and exam_date in elective_counts_by_date_program:
            del elective_counts_by_date_program[exam_date]

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
        """Precompute program/year conflict resources for one course.

        Profiles are immutable summaries used during recursive search.  They
        avoid repeatedly walking ``course.programs`` for every candidate date.
        """
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
        # This conservative rule prevents an elective copy of the same
        # program/year from weakening a mandatory conflict requirement.
        elective_keys.difference_update(
            obligatory_keys
        )

        mandatory_programs = {
            program.program_number
            for program in course.programs
            if (
                program.status.strip().lower()
                != "elective"
            )
        }
        elective_programs = {
            program.program_number
            for program in course.programs
            if (
                program.status.strip().lower()
                == "elective"
            )
        }
        elective_programs.difference_update(mandatory_programs)

        return _CourseProfile(
            course=course,
            obligatory_keys=frozenset(
                obligatory_keys
            ),
            elective_keys=frozenset(
                elective_keys
            ),
            all_keys=frozenset(
                obligatory_keys.union(elective_keys)
            ),
            elective_programs=frozenset(
                elective_programs
            ),
        )

    @staticmethod
    def _profile_weight(
        profile: _CourseProfile,
    ) -> tuple[int, int]:
        """Place courses with more conflict resources earlier in the search.

        This heuristic does not change which schedules are valid.  It only
        changes search order so highly constrained courses are placed earlier,
        causing impossible branches to fail sooner.
        """
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
        """Return True when no usable date belongs to two exam periods.

        Disjoint period date sets allow a cheaper Cartesian-product path
        because same-date cross-period conflicts cannot occur.
        """
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
        """Reject duplicated course IDs before recursion creates bad output.

        The output and manual-edit flows identify exams by course number.  A
        duplicate course number would make later selection, comparison, and
        undo/redo behavior ambiguous.
        """
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
        """Return course copies containing only rows for one semester.

        A course can appear in multiple program/semester rows.  For period
        generation, only enrollments matching the period semester are relevant,
        so this helper creates narrowed course copies before recursion starts.
        """
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

def _remove_one_date(
    index: dict,
    key,
    exam_date: date,
) -> None:
    """Remove one date from an index and delete empty buckets.

    The helper keeps _remove concise and ensures indexes do not retain empty
    lists that could later be mistaken for active constraint state.
    """
    dates = index[key]
    dates.remove(exam_date)
    if not dates:
        del index[key]
