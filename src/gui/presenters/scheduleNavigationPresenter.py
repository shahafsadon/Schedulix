"""Presenter for navigating and visualizing generated schedules (SCRUM-126).

After SCRUM-125 stores the generated exam systems in the cache, the output
screen must let the user browse them one at a time: move to the next or previous
system, see a "system X of Y" counter, and read the current system laid out by
semester and moed with its scheduled exams.

Following the MVP pattern, this presenter holds no customTkinter code. It owns
the navigation state (which system is currently shown) and turns the raw
ExamSystem objects into a flat, display-ready structure the View can render
directly. It also owns the Part 4 result-screen actions: snapshots, comparison,
manual moves, day highlighting, and undo/redo. It does not generate schedules
and it does not write exported files.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import Enum
from time import perf_counter

from application.commands import ScheduleModificationCommand, UndoRedoManager
from application.cache_manager import CacheManager
from constraint_settings import SchedulingConstraintSettings
from ranking_settings import RankedExamSystem, RankingSettings, ScheduleMetrics
from scheduling.batchIterator import iter_exam_system_batches
from scheduling.dayLoadAnalyzer import DayLoadAnalyzer, DayStatus
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.manualScheduleEditor import ManualScheduleEditor
from scheduling.qualityTagCalculator import QualityTagCalculator
from scheduling.rankedResultsBuffer import RankedResultsBuffer
from scheduling.scheduleDiffService import ScheduleDiffService
from scheduling.scheduleIntrospection import flatten_exam_system
from scheduling.scheduleMetricsCalculator import ScheduleMetricsCalculator
from scheduling.schedulePenaltyScorer import SchedulePenaltyScorer
from scheduling.scheduleRanker import ScheduleRanker
from scheduling.scheduleSnapshot import ScheduleSnapshot, SnapshotManager
from scheduling.scheduleRankingService import ScheduleRankingService

# Stable display order for semesters and moedim, matching the Version 1.0 output
# writer so the GUI shows systems in the same order as the exported file.
SEMESTER_ORDER = {"FALL": 0, "SPRI": 1, "SUMM": 2}
MOED_ORDER = {"Aleph": 0, "Bet": 1, "Gimel": 2}
logger = logging.getLogger(__name__)


class ResultMode(str, Enum):
    """Explicit display state for the output navigation screen."""

    UNRANKED_GENERATED = "unranked_generated"
    LIVE_RANKED_PREVIEW = "live_ranked_preview"
    FINAL_RANKED = "final_ranked"


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
class DayStatusView:
    """Small display model for one highlighted calendar day."""

    iso_date: str
    status: str
    label: str
    exam_count: int
    details: str


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
class RankingApplyResult:
    """Display-ready result of applying a ranking order."""

    success: bool
    message: str
    ranked_count: int = 0
    elapsed_seconds: float = 0.0
    ranked_schedules: list[RankedExamSystem] | None = None


@dataclass(frozen=True)
class ProgressiveRankingUpdate:
    """One live or terminal update from background ranking."""

    run_id: int
    ranked_schedules: list[RankedExamSystem]
    is_partial: bool
    processed_count: int
    total_count: int
    displayed_count: int
    message: str


@dataclass(frozen=True)
class SnapshotSummaryView:
    """One saved schedule version shown in the GUI."""

    name: str
    created_at: str
    quality_tag: str


@dataclass(frozen=True)
class SnapshotComparisonView:
    """Display-ready comparison between two saved schedule snapshots."""

    header: str
    first_name: str
    second_name: str
    first_quality: str
    second_quality: str
    first_penalty: str
    second_penalty: str
    quality_change_label: str
    quality_change_status: str
    penalty_delta_label: str
    penalty_delta_status: str
    changed_rows: list["SnapshotChangeRowView"]
    empty_message: str


@dataclass(frozen=True)
class SnapshotChangeRowView:
    """One changed exam row formatted for the GUI comparison panel."""

    change_label: str
    course_label: str
    period_label: str
    old_date: str
    new_date: str


@dataclass(frozen=True)
class GuiActionResult:
    """Result text for Part 4 GUI actions."""

    success: bool
    message: str
    details: str = ""
    comparison: SnapshotComparisonView | None = None


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
    day_status_by_iso_date: dict[str, DayStatusView] = field(default_factory=dict)
    quality_tag: str | None = None
    is_fallback: bool = False
    penalty_score: float | None = None
    penalty_details: tuple[str, ...] = ()


# Date format required by the output specification (DD-MM-YYYY).
_DATE_FORMAT = "%d-%m-%Y"
_EMPTY_OPTION = "No options available"


def _without_requirement_id(text: str) -> str:
    """Remove an internal requirement prefix from a user-facing message."""
    if text.startswith("Req ") and ": " in text:
        return text.split(": ", 1)[1]
    return text


class ScheduleNavigationPresenter:
    """Owns the current-system index and builds display-ready system views."""

    def __init__(
        self,
        schedules: list[ExamSystem | RankedExamSystem],
        cache_manager: CacheManager | None = None,
        active_ranking: RankingSettings | None = None,
        result_mode: str | ResultMode | None = None,
    ) -> None:
        """Create the presenter over the list of generated exam systems.

        Args:
            schedules: raw exam systems or ranked wrappers read from the cache.
                May be empty.
            cache_manager: the shared application cache.  When provided,
                successful ``apply_ranking()`` calls persist the new ranking
                settings and ordered schedules to disk (SCRUM-184).  When
                ``None`` the presenter still functions correctly but ranking
                choices are session-only.
            active_ranking: ranking criteria already chosen in the workflow.
                Live preview batches use this order immediately.
        """
        self._cache = cache_manager
        self._schedules: list[ExamSystem] = []
        self._ranked_schedules: list[RankedExamSystem] = []
        self._generated_schedules: list[ExamSystem] = []

        self._replace_schedules(schedules)
        self._result_mode = self._normalize_result_mode(result_mode, schedules)
        # Keep the full generated universe separate from ranked previews.
        # Raw schedules mean the presenter was opened from normal generation;
        # ranked wrappers may only be a derived Top-N view, so they are not
        # automatically treated as the complete source.
        if self._ranked_schedules:
            self._generated_schedules = []
        else:
            self._generated_schedules = self._schedules
        if cache_manager is not None:
            cached_generated = getattr(cache_manager, "get_generated_schedules", None)
            if callable(cached_generated):
                generated_schedules = cached_generated()
                if generated_schedules:
                    self._generated_schedules = generated_schedules

        # Start on the first system; stays at 0 when there are no systems.
        self._index = 0

        # Live preview metadata (populated by update_schedules).
        self._is_partial: bool = False
        self._systems_seen: int = 0
        self._displayed_count: int = 0

        # The last ranking successfully applied by the user.  Used to
        # automatically re-rank every incoming live batch (SCRUM-183).
        self._active_ranking: RankingSettings = active_ranking or RankingSettings([])
        self._snapshot_manager = SnapshotManager()
        self._day_load_analyzer = DayLoadAnalyzer()
        self._diff_service = ScheduleDiffService()
        self._quality_calculator = QualityTagCalculator()
        self._metrics_calculator = ScheduleMetricsCalculator()
        self._penalty_scorer = SchedulePenaltyScorer()
        # One editor is shared by the date picker and the command. The picker
        # asks it which dates are safe, then the command applies the same rule.
        self._manual_editor = ManualScheduleEditor()
        self._undo_redo = UndoRedoManager()

        current = self.current_system()
        if current is not None:
            self._snapshot_manager.set_active_schedule(
                current,
                self._current_metrics(),
            )

    # ------------------------------------------------------------------
    # Live preview metadata
    # ------------------------------------------------------------------

    @property
    def is_partial(self) -> bool:
        """True while background generation is still running."""
        return self._is_partial

    @property
    def result_mode(self) -> ResultMode:
        """Return whether the presenter is showing generated, preview, or ranked data."""
        return self._result_mode

    @property
    def is_final_ranked(self) -> bool:
        """True when the displayed order is a completed ranked result set."""
        return self._result_mode == ResultMode.FINAL_RANKED

    @property
    def systems_seen(self) -> int:
        """Total number of systems produced by the generator so far."""
        return self._systems_seen

    @property
    def displayed_count(self) -> int:
        """Number of systems currently held in the presenter."""
        return self._displayed_count

    def update_schedules(
        self,
        new_schedules: list[ExamSystem | RankedExamSystem],
        is_partial: bool,
        systems_seen: int,
        displayed_count: int,
    ) -> None:
        """Safely replace the schedule list with a new live batch.

        The navigation index is *clamped* rather than reset so that the user's
        current pagination position survives every incremental batch pushed by
        the background generator.  If the list shrank (shouldn't happen in
        practice but is safe to handle) the index is moved to the last valid
        position.

        When an active ranking has been applied (SCRUM-183), the incoming batch
        is automatically ranked before being stored so the display order is
        always consistent with the user's chosen ranking criteria.

        Args:
            new_schedules:   The full updated list coming from the generator.
            is_partial:      True when generation is still running.
            systems_seen:    How many systems the generator has produced so far.
            displayed_count: How many systems are in ``new_schedules``.
        """
        # The presenter accepts both raw legacy schedules and ranked updates
        # supplied by callers. Reapplying the active order keeps that boundary
        # deterministic; the list is bounded to the live preview size.
        if self._active_ranking.priority_list and new_schedules:
            service = ScheduleRankingService()
            try:
                if new_schedules and isinstance(new_schedules[0], RankedExamSystem):
                    outcome = service.rerank(new_schedules, self._active_ranking)
                else:
                    outcome = service.rank_generated_schedules(
                        new_schedules, self._active_ranking
                    )
                new_schedules = outcome.ranked_schedules
            except (AttributeError, TypeError, ValueError) as error:
                # Never crash the live-update pipeline due to a ranking error;
                # log the reason and keep the incoming generation order.
                logger.warning("Live preview ranking failed: %s", error)

        is_ranked_update = bool(
            new_schedules and isinstance(new_schedules[0], RankedExamSystem)
        )
        is_first_ranked_update = is_ranked_update and not self._ranked_schedules
        is_final_ranked_update = is_ranked_update and self._is_partial and not is_partial
        should_preserve_current = not (
            is_first_ranked_update or is_final_ranked_update
        )
        current_key = self._current_ranked_key() if should_preserve_current else None
        current_system = self.current_system() if should_preserve_current else None

        self._replace_schedules(new_schedules)
        self._is_partial = is_partial
        self._result_mode = (
            ResultMode.LIVE_RANKED_PREVIEW
            if is_partial
            else self._normalize_result_mode(None, new_schedules)
        )
        self._systems_seen = systems_seen
        self._displayed_count = displayed_count

        if should_preserve_current:
            self._restore_or_reset_index(
                current_key=current_key,
                current_system=current_system,
            )
        else:
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
            day_status_by_iso_date=self._day_status_views(system),
            quality_tag=self._current_quality_tag(),
            is_fallback=self._current_is_fallback(),
            penalty_score=self._current_penalty_score(),
            penalty_details=self._current_penalty_details(),
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
        preserve_current: bool = True,
    ) -> None:
        """
        Replace the display order while preserving the current system if found.

        This supports ranking-only changes: the generated systems stay cached,
        and the presenter swaps to the new order without resetting the user's
        selected system unnecessarily.
        """
        current_key = self._current_ranked_key() if preserve_current else None
        current_system = self.current_system() if preserve_current else None

        self._replace_schedules(ranked_schedules)
        self._result_mode = ResultMode.FINAL_RANKED
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

    # ------------------------------------------------------------------
    # Part 4 GUI actions
    # ------------------------------------------------------------------

    @property
    def can_undo_manual_move(self) -> bool:
        """Return True when the GUI can undo a manual move."""
        return self._undo_redo.undo_count > 0

    @property
    def can_redo_manual_move(self) -> bool:
        """Return True when the GUI can redo a manual move."""
        return self._undo_redo.redo_count > 0

    def snapshot_summaries(self) -> list[SnapshotSummaryView]:
        """Return saved snapshots for the sidebar list."""
        return [
            SnapshotSummaryView(
                name=snapshot.name,
                created_at=snapshot.created_at.strftime("%d-%m-%Y %H:%M"),
                quality_tag=self._friendly_quality_label(snapshot.quality_tag),
            )
            for snapshot in self._snapshot_manager.list_snapshots()
        ]

    def save_snapshot(self, name: str) -> GuiActionResult:
        """Save an independent named copy of the current schedule.

        Later manual moves cannot change this saved version.
        """
        system = self.current_system()
        if system is None:
            return GuiActionResult(False, "No schedule is available to save.")

        # Save the schedule together with the values used to describe its quality.
        metrics = self._current_metrics()
        quality = self._quality_calculator.calculate(metrics)
        self._snapshot_manager.set_active_schedule(system, metrics)

        try:
            snapshot = self._snapshot_manager.save_current(
                name,
                quality_tag=quality.tag,
                penalty_score=self._current_penalty_score(),
            )
        except (KeyError, ValueError) as error:
            return GuiActionResult(False, str(error))

        return GuiActionResult(
            True,
            f"Snapshot '{snapshot.name}' was saved.",
        )

    def load_snapshot(self, name: str) -> GuiActionResult:
        """Replace the visible schedule with a saved copy.

        Loading a snapshot does not generate new schedules. Old move history is
        cleared because it belongs to the schedule that was visible before.
        """
        try:
            snapshot = self._snapshot_manager.load(name)
        except (KeyError, ValueError) as error:
            return GuiActionResult(False, str(error))

        self._replace_current_schedule(snapshot.schedule, snapshot.metrics)
        self._undo_redo.clear()
        return GuiActionResult(
            True,
            f"Snapshot '{snapshot.name}' was loaded.",
        )

    def delete_snapshot(self, name: str) -> GuiActionResult:
        """Delete one saved snapshot from the sidebar."""
        try:
            self._snapshot_manager.delete(name)
        except (KeyError, ValueError) as error:
            return GuiActionResult(False, str(error))

        return GuiActionResult(True, f"Snapshot '{name}' was deleted.")

    def compare_snapshots(
        self,
        first_name: str,
        second_name: str,
    ) -> GuiActionResult:
        """Compare two saved versions by dates and available score data."""
        try:
            first = self._snapshot_by_name(first_name)
            second = self._snapshot_by_name(second_name)
        except (KeyError, ValueError) as error:
            return GuiActionResult(False, str(error))

        if first.name == second.name:
            return GuiActionResult(
                False,
                "Choose two different snapshots to compare.",
            )

        # The service reads both copies and does not change either snapshot.
        comparison = self._diff_service.compare(first, second)
        lines = self._comparison_lines(comparison, first, second)
        comparison_view = self._comparison_view(comparison, first, second)
        return GuiActionResult(
            True,
            f"Compared '{first.name}' with '{second.name}'.",
            details="\n".join(lines),
            comparison=comparison_view,
        )

    def manual_move_course_options(self) -> list[str]:
        """Return clear labels for every exam that the user can move.

        The label includes the semester and moed so equal course numbers are
        still easy to tell apart.
        """
        system = self.current_system()
        if system is None:
            return []

        return [
            self._manual_move_option_label(location)
            for location in sorted(
                flatten_exam_system(system),
                key=lambda item: (
                    item.course_id,
                    item.semester,
                    item.moed,
                    item.exam_date,
                ),
            )
        ]

    def manual_move_date_options(self, course_label: str) -> list[str]:
        """Return only safe new dates for the selected exam.

        The current date is not useful. Dates that would create a critical
        conflict are also hidden, so the user does not select a date that the
        application already knows it must reject.
        """
        location = self._manual_move_target_from_label(course_label)
        if location is None:
            return []

        system = self.current_system()
        if system is None:
            return []

        safe_dates: list[str] = []
        for candidate in sorted(self._available_dates_for_location(location)):
            if candidate == location.exam_date:
                continue

            # Reuse the domain editor instead of duplicating critical-conflict
            # logic in the presenter. This work is small because one exam
            # period normally contains only a limited number of active dates.
            result = self._manual_editor.move_exam(
                system,
                location.course_id,
                candidate,
                source_semester=location.semester,
                source_moed=location.moed,
                source_date=location.exam_date,
                constraint_settings=self._constraint_settings(),
                available_dates={candidate},
                include_impact=False,
            )
            if result.success:
                safe_dates.append(candidate.strftime(_DATE_FORMAT))

        return safe_dates

    def apply_manual_move(
        self,
        course_label: str,
        target_date_text: str,
    ) -> GuiActionResult:
        """Move one exact exam through a command that supports Undo and Redo."""
        system = self.current_system()
        if system is None:
            return GuiActionResult(False, "No schedule is available to edit.")

        location = self._manual_move_target_from_label(course_label)
        if location is None:
            return GuiActionResult(False, "Choose a course before applying a move.")

        # The command keeps enough old data to restore this move later.
        command = ScheduleModificationCommand(
            schedule_getter=self._required_current_system,
            schedule_setter=self._replace_current_schedule,
            course_id=location.course_id,
            new_date=target_date_text,
            source_semester=location.semester,
            source_moed=location.moed,
            source_date=location.exam_date,
            editor=self._manual_editor,
            constraint_settings=self._constraint_settings(),
            available_dates=self._available_dates_for_location(location),
        )
        # Only a successful move enters the Undo history.
        result = self._undo_redo.execute(command)
        if not result.success:
            return GuiActionResult(False, result.message)

        details = self._impact_details(getattr(result.data, "impact", None))
        return GuiActionResult(True, result.message, details=details)

    def undo_manual_move(self) -> GuiActionResult:
        """Undo the latest manual move without regenerating schedules."""
        result = self._undo_redo.undo()
        return GuiActionResult(result.success, result.message)

    def redo_manual_move(self) -> GuiActionResult:
        """Redo the latest undone manual move without regenerating schedules."""
        result = self._undo_redo.redo()
        return GuiActionResult(result.success, result.message)

    def _replace_current_schedule(
        self,
        schedule: ExamSystem,
        metrics: ScheduleMetrics | None = None,
    ) -> None:
        """Replace the visible schedule and refresh its saved display values.

        Other generated schedules keep their current order and are not changed.
        """
        if not self._schedules:
            return

        # Keep the active list and the raw generated list pointing to the same
        # updated schedule so navigation and later ranking show the move.
        old_system = self._schedules[self._index]
        self._schedules[self._index] = schedule

        for index, generated in enumerate(self._generated_schedules):
            if generated is old_system:
                self._generated_schedules[index] = schedule
                break

        if self._ranked_schedules:
            ranked = self._ranked_schedules[self._index]
            updated_metrics = metrics or self._metrics_calculator.calculate(
                schedule,
                ranked.key,
            )
            self._ranked_schedules[self._index] = replace(
                ranked,
                exam_system=schedule,
                metrics=updated_metrics,
                penalty_score=self._penalty_score_for_system(schedule),
                penalty_details=self._penalty_details_for_system(schedule),
            )
            metrics = updated_metrics

        self._snapshot_manager.set_active_schedule(
            schedule,
            metrics or self._current_metrics(),
        )

    def _required_current_system(self) -> ExamSystem:
        """Return the active system or fail clearly."""
        system = self.current_system()
        if system is None:
            raise ValueError("No current schedule is available.")
        return system

    def _current_metrics(self) -> ScheduleMetrics | None:
        """Return current metrics, calculating them when needed."""
        ranked_system = self.current_ranked_system()
        if ranked_system is not None:
            return ranked_system.metrics

        system = self.current_system()
        if system is None:
            return None

        return self._metrics_calculator.calculate(
            system,
            schedule_id=max(self.position(), 1),
        )

    def _snapshot_by_name(self, name: str) -> ScheduleSnapshot:
        """Read a snapshot by name through the manager API."""
        for snapshot in self._snapshot_manager.list_snapshots():
            if snapshot.name == name.strip():
                return snapshot
        raise KeyError(f"Snapshot was not found: {name.strip()}.")

    def _constraint_settings(self) -> SchedulingConstraintSettings | None:
        """Read active constraints from cache when the GUI has one."""
        if self._cache is None:
            return None

        getter = getattr(self._cache, "get_constraint_settings", None)
        if getter is None:
            return None

        return getter()

    def _day_status_views(
        self,
        system: ExamSystem,
    ) -> dict[str, DayStatusView]:
        """Build display data for busy, overloaded, and conflict days."""
        statuses = self._day_load_analyzer.analyze(
            system,
            self._constraint_settings(),
        )
        views: dict[str, DayStatusView] = {}

        for status in statuses:
            iso = status.exam_date.isoformat()
            details = "\n".join(
                violation.explanation for violation in status.violations
            )
            if not details:
                details = f"{status.exam_count} exam(s) scheduled on this date."

            views[iso] = DayStatusView(
                iso_date=iso,
                status=status.status.value,
                label=_day_status_label(status.status),
                exam_count=status.exam_count,
                details=details,
            )

        return views

    def _current_quality_tag(self) -> str | None:
        """Return a small quality label for the active schedule."""
        metrics = self._current_metrics()
        if metrics is None:
            return None
        return self._quality_calculator.calculate(metrics).tag

    def _current_is_fallback(self) -> bool:
        """Return True when the current ranked schedule is a fallback."""
        ranked = self.current_ranked_system()
        return bool(ranked is not None and ranked.is_fallback)

    def _current_penalty_score(self) -> float | None:
        """Return the stored or freshly calculated soft-constraint penalty."""
        ranked = self.current_ranked_system()
        if ranked is not None and ranked.penalty_score is not None:
            return ranked.penalty_score

        system = self.current_system()
        if system is None:
            return None
        return self._penalty_score_for_system(system)

    def _current_penalty_details(self) -> tuple[str, ...]:
        """Return readable penalty details for the current fallback schedule."""
        ranked = self.current_ranked_system()
        if ranked is not None and ranked.penalty_details:
            return tuple(
                _without_requirement_id(detail)
                for detail in ranked.penalty_details
            )

        system = self.current_system()
        if system is None:
            return ()
        return tuple(
            _without_requirement_id(detail)
            for detail in self._penalty_details_for_system(system)
        )

    def _penalty_score_for_system(self, system: ExamSystem) -> float:
        """Calculate the soft-constraint penalty for ``system``."""
        return self._penalty_scorer.score(
            system,
            self._constraint_settings(),
        ).total_score

    def _penalty_details_for_system(self, system: ExamSystem) -> tuple[str, ...]:
        """Calculate display-ready soft-constraint violations for ``system``."""
        return self._penalty_scorer.score(
            system,
            self._constraint_settings(),
        ).details

    def _available_dates_for_course(self, course_id: str) -> set[date]:
        """Return dates for the first matching course-period exam.

        New GUI code uses ``_available_dates_for_location`` so a course that
        appears in Aleph and Bet stays unambiguous. This helper remains for
        older callers that only know a course id.
        """
        system = self.current_system()
        if system is None:
            return set()

        location = next(
            (
                item
                for item in flatten_exam_system(system)
                if item.course_id == course_id
            ),
            None,
        )
        if location is None:
            return set()

        return self._available_dates_for_location(location)

    def _available_dates_for_location(self, location) -> set[date]:
        """Return allowed dates for one exact semester and moed."""
        dates: set[date] = {location.exam_date}
        if self._cache is None:
            return dates

        periods_getter = getattr(self._cache, "get_exam_periods", None)
        if periods_getter is None:
            return dates

        for period in periods_getter():
            if period.semester != location.semester or period.moed != location.moed:
                continue

            blocked = set(period.excluded_dates)
            current = period.start_date
            while current <= period.end_date:
                if current not in blocked:
                    dates.add(current)
                current += timedelta(days=1)

        return dates

    @staticmethod
    def _manual_move_option_label(location) -> str:
        """Build one clear GUI label for a course-period exam."""
        return (
            f"{location.course_id} | {location.semester} {location.moed} | "
            f"{location.exam_date.strftime(_DATE_FORMAT)} | "
            f"{location.course_name}"
        )

    def _manual_move_target_from_label(self, course_label: str):
        """Return the exact exam selected in the manual-move control."""
        text = course_label.strip()
        if not text or text == _EMPTY_OPTION:
            return None

        system = self.current_system()
        if system is None:
            return None

        for location in flatten_exam_system(system):
            if self._manual_move_option_label(location) == text:
                return location
        return None

    @staticmethod
    def _comparison_lines(
        comparison,
        first: ScheduleSnapshot,
        second: ScheduleSnapshot,
    ) -> list[str]:
        """Format snapshot diff rows for a small GUI text panel."""
        lines = [
            f"{comparison.first_name} -> {comparison.second_name}",
            "",
        ]
        if comparison.penalty_delta is not None:
            lines.append(
                "Penalty score (lower is better): "
                f"{first.penalty_score:g} -> {second.penalty_score:g} "
                f"(delta {comparison.penalty_delta:+g})"
            )
            lines.append("")
        elif first.quality_tag or second.quality_tag:
            lines.append(
                "Quality label: "
                f"{first.quality_tag or 'unknown'} -> "
                f"{second.quality_tag or 'unknown'}"
            )
            lines.append("")

        if not comparison.changed_courses:
            lines.append("No changed courses.")
        else:
            for row in comparison.changed_courses:
                lines.append(
                    (
                        f"{row.course_id} - {row.course_name}: "
                        f"{row.semester} {row.moed}, "
                        f"{_format_optional_date(row.old_date)} -> "
                        f"{_format_optional_date(row.new_date)} "
                        f"({row.change_type})"
                    )
                )

        return lines

    def _comparison_view(
        self,
        comparison,
        first: ScheduleSnapshot,
        second: ScheduleSnapshot,
    ) -> SnapshotComparisonView:
        """Build the structured comparison model rendered by the GUI."""
        rows = [
            SnapshotChangeRowView(
                change_label=self._friendly_change_label(row.change_type),
                course_label=f"{row.course_id} - {row.course_name}",
                period_label=f"{row.semester} {row.moed}",
                old_date=_format_optional_date(row.old_date),
                new_date=_format_optional_date(row.new_date),
            )
            for row in comparison.changed_courses
        ]
        first_quality = self._friendly_quality_label(first.quality_tag)
        second_quality = self._friendly_quality_label(second.quality_tag)
        return SnapshotComparisonView(
            header=(
                f"Comparison: {comparison.first_name} "
                f"\u2192 {comparison.second_name}"
            ),
            first_name=first.name,
            second_name=second.name,
            first_quality=first_quality,
            second_quality=second_quality,
            first_penalty=self._format_penalty(first.penalty_score),
            second_penalty=self._format_penalty(second.penalty_score),
            quality_change_label=self._format_quality_change(
                first_quality,
                second_quality,
            ),
            quality_change_status=self._quality_change_status(
                first_quality,
                second_quality,
            ),
            penalty_delta_label=self._format_penalty_delta(
                first.penalty_score,
                second.penalty_score,
                comparison.penalty_delta,
            ),
            penalty_delta_status=self._penalty_delta_status(
                comparison.penalty_delta,
            ),
            changed_rows=rows,
            empty_message="No exam date changes between these snapshots.",
        )

    @staticmethod
    def _friendly_quality_label(quality_tag) -> str:
        """Return a user-facing quality label instead of a raw enum value."""
        if quality_tag is None:
            return "Unknown"

        value = getattr(quality_tag, "value", quality_tag)
        text = str(value)
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        text = text.replace("_", " ").strip()
        return text.title() if text else "Unknown"

    @staticmethod
    def _friendly_change_label(change_type: str) -> str:
        """Return a concise title for one diff row."""
        labels = {
            "moved": "Moved exam",
            "added": "Added exam",
            "removed": "Removed exam",
        }
        return labels.get(change_type, change_type.replace("_", " ").title())

    @staticmethod
    def _format_penalty(penalty_score: float | None) -> str:
        """Format optional penalty values for compact GUI display."""
        return f"{penalty_score:g}" if penalty_score is not None else "n/a"

    @classmethod
    def _format_quality_change(cls, first_quality: str, second_quality: str) -> str:
        """Format the before/after quality movement as the primary verdict."""
        status = cls._quality_change_status(first_quality, second_quality)
        return (
            f"Quality change: {first_quality} \u2192 {second_quality} "
            f"\u2014 {status}"
        )

    @staticmethod
    def _quality_change_status(first_quality: str, second_quality: str) -> str:
        """Classify quality movement using the review-friendly tag order."""
        quality_order = {
            "Risky": 0,
            "Needs Review": 1,
            "Good": 2,
            "Excellent": 3,
        }
        first_rank = quality_order.get(first_quality)
        second_rank = quality_order.get(second_quality)
        if first_rank is None or second_rank is None:
            return "unchanged" if first_quality == second_quality else "changed"
        if second_rank > first_rank:
            return "improved"
        if second_rank < first_rank:
            return "worsened"
        return "unchanged"

    @classmethod
    def _format_penalty_delta(
        cls,
        first_penalty: float | None,
        second_penalty: float | None,
        penalty_delta: float | None,
    ) -> str:
        """Format constraint-penalty movement separately from quality."""
        first_text = cls._format_penalty(first_penalty)
        second_text = cls._format_penalty(second_penalty)
        if penalty_delta is None:
            return f"Constraint penalty: {first_text} \u2192 {second_text} \u2014 n/a"
        if penalty_delta < 0:
            return (
                f"Constraint penalty: {first_text} \u2192 {second_text} "
                "\u2014 improved"
            )
        if penalty_delta > 0:
            return (
                f"Constraint penalty: {first_text} \u2192 {second_text} "
                "\u2014 worsened"
            )
        return f"Constraint penalty: {first_text} \u2192 {second_text} \u2014 unchanged"

    @staticmethod
    def _penalty_delta_status(penalty_delta: float | None) -> str:
        """Classify the score delta so the GUI can color it consistently."""
        if penalty_delta is None or penalty_delta == 0:
            return "neutral"
        return "improved" if penalty_delta < 0 else "worse"

    @staticmethod
    def _impact_details(impact) -> str:
        """Format manual-move impact analysis for the GUI."""
        if impact is None:
            return "No impact analysis is available."

        sections = [
            ("Resolved issues", impact.resolved_issues),
            ("New issues", impact.new_issues),
            ("Unchanged issues", impact.unchanged_issues),
        ]
        lines: list[str] = []

        for title, issues in sections:
            if not issues:
                continue
            lines.append(title + ":")
            for issue in issues:
                lines.append(f"- {issue.explanation}")
            lines.append("")

        if not lines:
            return "No issue changes were detected."

        return "\n".join(lines).strip()

    def rank_progressively(
        self,
        ranking_settings: RankingSettings,
        run_id: int,
        on_update: Callable[[ProgressiveRankingUpdate], None] | None = None,
        cancellation_token=None,
        batch_size: int = 1000,
        preview_limit: int = 50,
        min_update_interval_seconds: float = 0.35,
        ranking_service: ScheduleRankingService | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> ProgressiveRankingUpdate:
        """Rank generated schedules in bounded batches for live GUI preview.

        This ranks the already generated schedule list without regenerating
        dates. Partial updates emit a bounded Top-N preview. The final update
        emits the full ranked list so completed ranked navigation can browse
        every generated schedule from best to worst.
        """
        source_schedules = self._ranking_source_schedules()
        total_count = len(source_schedules)
        if total_count == 0:
            return ProgressiveRankingUpdate(
                run_id=run_id,
                ranked_schedules=[],
                is_partial=False,
                processed_count=0,
                total_count=0,
                displayed_count=0,
                message="No schedules to rank.",
            )

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")
        if preview_limit <= 0:
            raise ValueError("preview_limit must be greater than zero.")
        if min_update_interval_seconds < 0:
            raise ValueError("min_update_interval_seconds cannot be negative.")

        self._active_ranking = ranking_settings
        if self._cache is not None:
            self._cache.set_ranking_settings(ranking_settings)

        service = ranking_service or ScheduleRankingService()
        preview = RankedResultsBuffer(
            ranking_settings=ranking_settings,
            preview_limit=preview_limit,
        )
        full_ranked_schedules: list[RankedExamSystem] = []

        final_update: ProgressiveRankingUpdate | None = None
        last_emit_at: float | None = None
        for batch in iter_exam_system_batches(
            source_schedules,
            batch_size,
            should_stop=lambda: bool(getattr(cancellation_token, "is_cancelled", False)),
        ):
            if batch.is_empty:
                continue

            outcome = service.rank_generated_batch(
                batch.schedules,
                ranking_settings,
                starting_schedule_id=batch.starting_schedule_id,
            )
            full_ranked_schedules.extend(outcome.ranked_schedules)
            ranked_preview = preview.add_ranked_batch(
                outcome.ranked_schedules,
                generated_count=batch.size,
                accepted_count=batch.size,
                processed_count=batch.size,
                ranking_seconds=outcome.elapsed_seconds,
            )

            if getattr(cancellation_token, "is_cancelled", False):
                break

            final_update = ProgressiveRankingUpdate(
                run_id=run_id,
                ranked_schedules=ranked_preview,
                is_partial=True,
                processed_count=preview.processed_schedules,
                total_count=total_count,
                displayed_count=len(ranked_preview),
                message=(
                    f"Live preview: showing temporary Top "
                    f"{len(ranked_preview):,} from "
                    f"{preview.processed_schedules:,} ranked so far."
                ),
            )
            now = clock()
            should_emit = (
                last_emit_at is None
                or now - last_emit_at >= min_update_interval_seconds
            )
            if on_update is not None and should_emit:
                on_update(final_update)
                last_emit_at = now

        if hasattr(service, "rerank"):
            final_outcome = service.rerank(
                full_ranked_schedules,
                ranking_settings,
            )
            ranked_schedules = final_outcome.ranked_schedules
        else:
            ranked_schedules = ScheduleRanker().rank(
                full_ranked_schedules,
                ranking_settings,
            )
        final_update = ProgressiveRankingUpdate(
            run_id=run_id,
            ranked_schedules=ranked_schedules,
            is_partial=False,
            processed_count=preview.processed_schedules,
            total_count=total_count,
            displayed_count=len(ranked_schedules),
            message=(
                f"Ranking complete. Showing all "
                f"{len(ranked_schedules):,} ranked schedule(s)."
            ),
        )

        if (
            self._cache is not None
            and not getattr(cancellation_token, "is_cancelled", False)
        ):
            self._cache.set_ranked_schedules(ranked_schedules)

        return final_update

    def apply_ranking(
        self,
        ranking_settings: RankingSettings,
        ranking_service: ScheduleRankingService | None = None,
    ) -> RankingApplyResult:
        """Rank existing generated systems without regenerating schedules."""
        if not self._schedules:
            return RankingApplyResult(
                success=False,
                message="No schedules to rank.",
            )

        service = ranking_service or ScheduleRankingService()
        source_schedules = self._ranking_source_schedules()

        if source_schedules:
            outcome = service.rank_generated_schedules(
                source_schedules,
                ranking_settings,
            )
            ranked_schedules = outcome.ranked_schedules
            elapsed_seconds = outcome.elapsed_seconds
        elif self._ranked_schedules:
            return RankingApplyResult(
                success=False,
                message=(
                    "Full generated schedule list is not available. "
                    "Regenerate schedules before changing ranking criteria."
                ),
                ranked_count=len(self._ranked_schedules),
                ranked_schedules=list(self._ranked_schedules),
            )
        else:
            outcome = service.rank_generated_schedules(
                self._schedules,
                ranking_settings,
            )
            ranked_schedules = outcome.ranked_schedules
            elapsed_seconds = outcome.elapsed_seconds

        self.apply_ranked_schedules(ranked_schedules, preserve_current=False)

        # Persist the ranking so future live batches are re-ranked automatically
        # (SCRUM-183: support ranking changes during background generation).
        self._active_ranking = ranking_settings

        # Durably persist the user's chosen ranking criteria and the newly
        # ordered schedule list to the permanent cache (SCRUM-184).  This is
        # intentionally skipped for session-only (no cache) callers so that
        # unit tests and headless code paths remain unaffected.
        if self._cache is not None:
            self._cache.set_ranking_settings(self._active_ranking)
            if not self.is_partial:
                self._cache.set_ranked_schedules(ranked_schedules)

        if ranking_settings.priority_list:
            message = f"Ranking applied to {len(ranked_schedules)} system(s)."
        else:
            message = "Ranking cleared; generation order restored."

        return RankingApplyResult(
            success=True,
            message=message,
            ranked_count=len(ranked_schedules),
            elapsed_seconds=elapsed_seconds,
            ranked_schedules=ranked_schedules,
        )

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

    def _ranking_source_schedules(self) -> list[ExamSystem]:
        """Return the generated schedules without making an extra full copy."""
        if self._generated_schedules:
            return self._generated_schedules
        return []

    def _restore_or_reset_index(
        self,
        current_key: int | None,
        current_system: ExamSystem | None,
    ) -> None:
        """Keep the same ranked item when possible, otherwise reset safely."""
        if not self._schedules:
            self._index = 0
            return

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

        self._index = min(self._index, len(self._schedules) - 1)

    @staticmethod
    def _normalize_result_mode(
        result_mode: str | ResultMode | None,
        schedules: list[ExamSystem | RankedExamSystem],
    ) -> ResultMode:
        """Resolve legacy/raw constructor input into an explicit display mode."""
        if isinstance(result_mode, ResultMode):
            return result_mode
        if isinstance(result_mode, str):
            try:
                return ResultMode(result_mode)
            except ValueError:
                pass
        if schedules and isinstance(schedules[0], RankedExamSystem):
            return ResultMode.FINAL_RANKED
        return ResultMode.UNRANKED_GENERATED

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


def _day_status_label(status: DayStatus) -> str:
    """Return short text for a day-load status."""
    if status == DayStatus.CONFLICT:
        return "Conflict"
    if status == DayStatus.OVERLOADED:
        return "Overloaded"
    if status == DayStatus.BUSY:
        return "Busy"
    return "Normal"


def _format_optional_date(value: date | None) -> str:
    """Format dates in snapshot comparison rows."""
    if value is None:
        return "-"
    return value.strftime(_DATE_FORMAT)
