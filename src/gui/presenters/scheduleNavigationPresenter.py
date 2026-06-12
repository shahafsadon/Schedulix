"""Presenter for navigating and visualizing generated schedules (SCRUM-126).

After SCRUM-125 stores the generated exam systems in the cache, the output
screen must let the user browse them one at a time: move to the next or previous
system, see a "system X of Y" counter, and read the current system laid out by
semester and moed with its scheduled exams.

Following the MVP pattern, this presenter holds no customTkinter code. It owns
the navigation state (which system is currently shown) and turns the raw
ExamSystem objects into a flat, display-ready structure the View can render
directly. It does not generate schedules and does not write files.
"""
from __future__ import annotations

from dataclasses import dataclass

from ranking_settings import RankedExamSystem, ScheduleMetrics
from scheduling.examScheduleGenerator import ExamSystem

# Stable display order for semesters and moedim, matching the Version 1.0 output
# writer so the GUI shows systems in the same order as the exported file.
SEMESTER_ORDER = {"FALL": 0, "SPRI": 1, "SUMM": 2}
MOED_ORDER = {"Aleph": 0, "Bet": 1, "Gimel": 2}


@dataclass(frozen=True)
class ExamRow:
    """One scheduled exam, flattened for display.

    All fields are plain strings so the View can place them directly into
    labels without reaching back into the domain objects.
    """

    exam_date: str          # formatted DD-MM-YYYY
    course_number: str
    course_name: str
    instructor: str
    status: str             # "Obligatory" / "Elective" (or "" if unknown)
    program_numbers: str    # comma-separated programs the course belongs to


@dataclass(frozen=True)
class MoedSection:
    """All exams of one (semester, moed) section within a system."""

    semester: str
    moed: str
    exams: list[ExamRow]


@dataclass(frozen=True)
class CalendarCell:
    """One day on the year calendar, with any exams scheduled on it.

    The calendar view uses these cells to know which days are exam days; a
    non-empty `exams` list tells the View to highlight the cell and to open a
    detail popup when it is clicked.
    """

    iso_date: str           # YYYY-MM-DD, used as a stable cell id
    year: int
    month: int              # 1..12
    day: int                # 1..31
    exams: list[ExamRow]    # may be empty (regular day)


@dataclass(frozen=True)
class MetricsSummaryView:
    """Calculated metrics for one ranked system, ready for display."""

    schedule_id: int
    min_mandatory_gap: int
    average_all_gap: float
    elective_collision_count: int
    mandatory_span: int
    max_exams_per_day: int


@dataclass(frozen=True)
class SystemView:
    """A full, display-ready view of the currently shown exam system.

    position and total drive the "System X of Y" counter; sections holds the
    exams grouped and ordered by semester then moed; calendar_year is the year
    the View should render as a 12-month grid.
    """

    position: int        # 1-based index of the current system
    total: int           # total number of systems available
    sections: list[MoedSection]
    calendar_year: int | None   # year shown on the annual calendar (None = empty)
    exams_by_iso_date: dict[str, list[ExamRow]]  # quick lookup for the calendar
    metrics_summary: MetricsSummaryView | None = None


# Date format required by the output specification (DD-MM-YYYY).
_DATE_FORMAT = "%d-%m-%Y"


class ScheduleNavigationPresenter:
    """Owns the current-system index and builds display-ready system views."""

    def __init__(
        self,
        schedules: list[ExamSystem | RankedExamSystem],
    ) -> None:
        """Create the presenter over the list of generated exam systems.

        Args:
            schedules: raw exam systems or ranked wrappers read from the cache.
                May be empty.
        """
        self._schedules: list[ExamSystem] = []
        self._ranked_schedules: list[RankedExamSystem] = []

        self._replace_schedules(schedules)

        # Start on the first system; stays at 0 when there are no systems.
        self._index = 0

    def has_schedules(self) -> bool:
        """Return True when there is at least one system to display."""
        return len(self._schedules) > 0

    def relevant_months(self) -> list[tuple[int, int]]:
        """Return the (year, month) pairs that contain an exam in ANY system.

        Only months that hold at least one exam across all generated systems
        are worth drawing. Computing this over every system (not just the
        current one) keeps the calendar's month list stable while the user
        navigates, so the grid is built once and never restructured.

        The result is sorted chronologically (year, then month).
        """
        months: set[tuple[int, int]] = set()
        for system in self._schedules:
            for schedule in system.period_schedules:
                for exam in schedule.scheduled_exams:
                    months.add((exam.exam_date.year, exam.exam_date.month))
        return sorted(months)

    def total(self) -> int:
        """Return how many systems are available for navigation."""
        return len(self._schedules)

    def position(self) -> int:
        """Return the 1-based index of the current system (0 if none)."""
        return self._index + 1 if self._schedules else 0

    def can_go_next(self) -> bool:
        """Return True when a next system exists after the current one."""
        return self._index < len(self._schedules) - 1

    def can_go_previous(self) -> bool:
        """Return True when a previous system exists before the current one."""
        return self._index > 0

    def next(self) -> None:
        """Advance to the next system, if there is one.

        Calling next at the last system does nothing, so the View can wire the
        button unconditionally and rely on can_go_next() to enable/disable it.
        """
        if self.can_go_next():
            self._index += 1

    def previous(self) -> None:
        """Go back to the previous system, if there is one.

        Calling previous at the first system does nothing, mirroring next().
        """
        if self.can_go_previous():
            self._index -= 1

    def current_view(self) -> SystemView | None:
        """Build the display-ready view of the current system.

        Returns None when there are no systems at all, so the View can show an
        empty-state message instead of an exam layout.
        """
        if not self._schedules:
            return None

        system = self._schedules[self._index]

        # Order the period schedules by semester then moed, the same way the
        # Version 1.0 output writer does, for a consistent presentation.
        ordered_schedules = sorted(
            system.period_schedules,
            key=lambda schedule: (
                SEMESTER_ORDER.get(schedule.semester, len(SEMESTER_ORDER)),
                MOED_ORDER.get(schedule.moed, len(MOED_ORDER)),
            ),
        )

        sections = [
            MoedSection(
                semester=schedule.semester,
                moed=schedule.moed,
                exams=self._build_rows(schedule),
            )
            for schedule in ordered_schedules
        ]

        # Build a quick "iso_date -> exams" index so the calendar view can
        # color each day in O(1) without re-walking every schedule.
        exams_by_iso_date: dict[str, list] = {}
        # Track the years used by this system to pick the calendar year:
        # we render the first (smallest) year that appears, matching the
        # natural reading order of the academic year.
        years_seen: list[int] = []
        for schedule in ordered_schedules:
            for exam in schedule.scheduled_exams:
                iso = exam.exam_date.strftime("%Y-%m-%d")
                row = self._build_row(exam)
                exams_by_iso_date.setdefault(iso, []).append(row)
                years_seen.append(exam.exam_date.year)

        calendar_year = min(years_seen) if years_seen else None

        return SystemView(
            position=self.position(),
            total=self.total(),
            sections=sections,
            calendar_year=calendar_year,
            exams_by_iso_date=exams_by_iso_date,
            metrics_summary=self._current_metrics_summary(),
        )

    def current_system(self) -> ExamSystem | None:
        """Return the currently selected raw exam system, if one exists."""
        if not self._schedules:
            return None
        return self._schedules[self._index]

    def current_ranked_system(self) -> RankedExamSystem | None:
        """Return the ranked wrapper for the displayed system, if available."""
        if not self._ranked_schedules:
            return None
        return self._ranked_schedules[self._index]

    def apply_ranked_schedules(
        self,
        ranked_schedules: list[RankedExamSystem],
    ) -> None:
        """
        Replace the display order while preserving the current system if found.

        This supports ranking-only changes: the generated systems stay cached,
        and the presenter swaps to the new order without resetting the user's
        selected system unnecessarily.
        """
        current_key = self._current_ranked_key()
        current_system = self.current_system()

        self._replace_schedules(ranked_schedules)
        self._index = 0

        if current_key is not None:
            for index, ranked_system in enumerate(self._ranked_schedules):
                if ranked_system.key == current_key:
                    self._index = index
                    return

        if current_system is not None:
            for index, system in enumerate(self._schedules):
                if system is current_system:
                    self._index = index
                    return

    def _build_rows(self, schedule) -> list[ExamRow]:
        """Flatten one period schedule's exams into display rows.

        Exams are sorted by date then course number so the order is stable and
        matches the exported file.
        """
        ordered_exams = sorted(
            schedule.scheduled_exams,
            key=lambda exam: (exam.exam_date, exam.course.course_number),
        )
        return [self._build_row(exam) for exam in ordered_exams]

    def _replace_schedules(
        self,
        schedules: list[ExamSystem | RankedExamSystem],
    ) -> None:
        """Normalize raw or ranked input into presenter state."""
        if schedules and isinstance(schedules[0], RankedExamSystem):
            self._ranked_schedules = list(schedules)
            self._schedules = [
                ranked_system.exam_system
                for ranked_system in self._ranked_schedules
            ]
            return

        self._ranked_schedules = []
        self._schedules = list(schedules)

    def _current_metrics_summary(self) -> MetricsSummaryView | None:
        """Return display metrics for the current ranked system."""
        ranked_system = self.current_ranked_system()
        if ranked_system is None:
            return None

        return self._metrics_to_view(ranked_system.metrics)

    def _current_ranked_key(self) -> int | None:
        """Return the stable key of the current ranked item, if present."""
        ranked_system = self.current_ranked_system()
        if ranked_system is None:
            return None

        return ranked_system.key

    @staticmethod
    def _metrics_to_view(
        metrics: ScheduleMetrics,
    ) -> MetricsSummaryView:
        """Copy domain metric values into a presenter-owned view object."""
        return MetricsSummaryView(
            schedule_id=metrics.schedule_id,
            min_mandatory_gap=metrics.min_mandatory_gap,
            average_all_gap=metrics.average_all_gap,
            elective_collision_count=metrics.elective_collision_count,
            mandatory_span=metrics.mandatory_span,
            max_exams_per_day=metrics.max_exams_per_day,
        )

    @staticmethod
    def _build_row(exam) -> ExamRow:
        """Turn one ScheduledExam into a display-ready ExamRow.

        program_numbers is a comma-separated string because a course may belong
        to several programs and we want one line on screen, not a list widget.
        status is taken from the first enrollment row for display, since the
        requirement type is typically the same across programs for a course.
        """
        course = exam.course
        # Deduplicate while preserving order, then join with commas.
        seen: set[str] = set()
        program_numbers: list[str] = []
        for enrollment in course.programs:
            if enrollment.program_number not in seen:
                seen.add(enrollment.program_number)
                program_numbers.append(enrollment.program_number)

        return ExamRow(
            exam_date=exam.exam_date.strftime(_DATE_FORMAT),
            course_number=course.course_number,
            course_name=course.name,
            instructor=course.instructor,
            status=course.programs[0].status if course.programs else "",
            program_numbers=", ".join(program_numbers),
        )
