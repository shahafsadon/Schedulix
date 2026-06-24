"""Output screen: review, edit, compare, and export generated exam schedules.

The screen keeps the existing passive MVP boundary: navigation state and
display models come from ``ScheduleNavigationPresenter`` while the view owns
layout, buttons, and file dialogs. Part 4 tools are shown here, but the real
schedule logic stays in the presenter and scheduling services.
"""
from __future__ import annotations

import calendar
from tkinter import filedialog
from typing import Callable

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.async_runner import AsyncScheduleRunner
from gui.presenters.exportPresenter import ExportPresenter, ExportStatus
from gui.presenters.scheduleNavigationPresenter import (
    DayStatusView,
    ExamRow,
    ProgressiveRankingUpdate,
    ResultMode,
    ScheduleNavigationPresenter,
)
from gui.screens.themeToggle import (
    THEME_BUTTON_WIDTH,
    ThemeButtonText,
    ThemeToggleCallback,
    current_theme_button_text,
    handle_theme_toggle,
)
from ranking_settings import RankingCriterion, RankingPreference, RankingSettings


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_WEEKDAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_PAGE_BG = ("#F3F6FB", "#0B1220")
_SURFACE = ("#FFFFFF", "#151B26")
_SUBTLE_SURFACE = ("#F8FAFC", "#101826")
_BORDER = ("#D8E2F0", "#2D3748")
_TEXT = ("#111827", "#F8FAFC")
_MUTED = ("#5F6368", "#A8A8A8")
_PRIMARY = "#2563EB"
_PRIMARY_HOVER = "#1D4ED8"
_CONTROL_BG = ("#F8FAFC", "#1F2937")
_CONTROL_BUTTON = ("#E2E8F0", "#334155")
_CONTROL_HOVER = ("#CBD5E1", "#475569")
_RESULT_CARD_BG = ("#F8FAFC", "#111827")
_INFO = "#2563EB"
_EXAM_DAY_COLOR = ("#DBEAFE", "#1E3A8A")
_EXAM_DAY_HOVER = ("#BFDBFE", "#274A9F")
_EXAM_DAY_TEXT = ("#0F172A", "#EAF2FF")
_SELECTED_DAY_COLOR = ("#2563EB", "#60A5FA")
_SELECTED_DAY_TEXT = ("#FFFFFF", "#0B1220")
_REGULAR_DAY_TEXT = ("#A8B0BA", "#64748B")
_BUSY_DAY_COLOR = ("#FEF3C7", "#78350F")
_BUSY_DAY_TEXT = ("#78350F", "#FEF3C7")
_OVERLOADED_DAY_COLOR = ("#FED7AA", "#7C2D12")
_OVERLOADED_DAY_TEXT = ("#7C2D12", "#FFEDD5")
_CONFLICT_DAY_COLOR = ("#FEE2E2", "#7F1D1D")
_CONFLICT_DAY_TEXT = ("#7F1D1D", "#FEE2E2")
_SUCCESS = "#2e7d32"
_ERROR = "#B00020"
_EMPTY_OPTION = "No options available"
_MESSAGE_POPUP_WIDTH = 430
_MESSAGE_POPUP_HEIGHT = 190

# Status banner colours: light-mode bg / dark-mode bg.
_BANNER_PARTIAL_BG = ("#FEF3C7", "#3B2800")
_BANNER_PARTIAL_TEXT = ("#92400E", "#FDE68A")
_BANNER_FINAL_BG = ("#D1FAE5", "#052E16")
_BANNER_FINAL_TEXT = ("#065F46", "#6EE7B7")

_RANKING_LABELS: dict[RankingCriterion, str] = {
    RankingCriterion.min_mandatory_gap: "Min mandatory gap (descending)",
    RankingCriterion.average_all_gap: "Average exam gap (descending)",
    RankingCriterion.elective_collision_count: "Elective collisions (descending)",
    RankingCriterion.mandatory_span: "Mandatory span (descending)",
    RankingCriterion.max_exams_per_day: "Max exams/day (descending)",
}

# Version 2.0 ranking settings currently accept descending order only.
# Keep the GUI aligned with the parser/validator contract so applying a ranking
# from the results screen cannot create invalid RankingSettings.
_RANKING_DIRECTION: dict[RankingCriterion, bool] = {
    RankingCriterion.min_mandatory_gap: True,
    RankingCriterion.average_all_gap: True,
    RankingCriterion.elective_collision_count: True,
    RankingCriterion.mandatory_span: True,
    RankingCriterion.max_exams_per_day: True,
}


class ScheduleNavigationScreen(ctk.CTkFrame):
    """Review generated exam systems with calendar, details, and export."""

    def __init__(
        self,
        master,
        presenter: ScheduleNavigationPresenter,
        export_presenter: ExportPresenter | None = None,
        on_back: Callable[[], None] | None = None,
        on_theme_toggle: ThemeToggleCallback | None = None,
        theme_button_text: ThemeButtonText = None,
        ranking_runner: AsyncScheduleRunner | None = None,
    ) -> None:
        super().__init__(master, corner_radius=0, fg_color=_PAGE_BG)
        self.presenter = presenter
        self._export_presenter = export_presenter
        self._on_back = on_back
        self._on_theme_toggle = on_theme_toggle
        self._theme_button_text = theme_button_text
        self._ranking_runner = ranking_runner or AsyncScheduleRunner()
        self._ranking_run_id = 0

        self._exam_cells: dict[str, ctk.CTkButton] = {}
        self._selected_iso_date: str | None = None
        self._current_exams_by_iso_date: dict[str, list[ExamRow]] = {}
        self._current_day_status_by_iso_date: dict[str, DayStatusView] = {}
        self._grid_built = False
        # Tracks which (year, month) cards have already been appended to the
        # calendar scroll area, enabling incremental DOM updates on live batches.
        self._built_months: set[tuple[int, int]] = set()
        self._metric_labels: dict[str, ctk.CTkLabel] = {}
        self._ranking_metric_labels: dict[str, ctk.CTkLabel] = {}
        self._ranking_criteria: list[RankingCriterion] = []
        self._ranking_rows_frame = None
        self._criterion_selector = None
        self._apply_ranking_button = None
        self._ranking_status_label = None
        self._theme_button: ctk.CTkButton | None = None
        self._snapshot_name_entry = None
        self._snapshot_first_selector = None
        self._snapshot_second_selector = None
        self._snapshot_list_label = None
        self._load_snapshot_button = None
        self._delete_snapshot_button = None
        self._compare_snapshot_button = None
        self._snapshot_status_label = None
        self._snapshot_compare_box = None
        self._move_course_selector = None
        self._move_date_selector = None
        self._move_status_label = None
        self._move_impact_box = None
        self._apply_move_button = None
        self._undo_move_button = None
        self._redo_move_button = None

        self._build()
        self._refresh()

    def _build(self) -> None:
        """Build the redesigned output review layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_metrics()
        self._build_main_area()
        self._build_footer()

    def _build_header(self) -> None:
        """Build title, counter, primary actions, and live-status banner."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Generated Exam Schedules",
            font=("Segoe UI", 24, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")

        self._counter_label = ctk.CTkLabel(
            header,
            text="",
            font=("Segoe UI", 13),
            text_color=_MUTED,
        )
        self._counter_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")

        if self._on_back is not None:
            ctk.CTkButton(
                actions,
                text="Back",
                width=86,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                command=self._on_back,
            ).grid(row=0, column=0, padx=(0, 8))

        self._prev_button = ctk.CTkButton(
            actions,
            text="< Previous",
            width=112,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=(_PRIMARY, "#93C5FD"),
            command=self._handle_previous,
        )
        self._prev_button.grid(row=0, column=1, padx=(0, 8))

        self._next_button = ctk.CTkButton(
            actions,
            text="Next >",
            width=96,
            command=self._handle_next,
        )
        self._next_button.grid(row=0, column=2, padx=(0, 8))

        self._save_button = None
        next_action_column = 3
        if self._export_presenter is not None:
            self._save_button = ctk.CTkButton(
                actions,
                text="Save Final System",
                width=122,
                fg_color=_PRIMARY,
                hover_color=_PRIMARY_HOVER,
                command=self._handle_save,
            )
            self._save_button.grid(row=0, column=3)
            next_action_column = 4

        if self._on_theme_toggle is not None:
            # Button text tells the user which mode the click will open.
            self._theme_button = ctk.CTkButton(
                actions,
                text=current_theme_button_text(self._theme_button_text),
                width=THEME_BUTTON_WIDTH,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                hover_color=("#DCE8FF", "#1E293B"),
                command=self._handle_theme_toggle,
            )
            self._theme_button.grid(
                row=0,
                column=next_action_column,
                padx=(8, 0),
            )

        self._status_banner = ctk.CTkFrame(
            header,
            fg_color=_BANNER_PARTIAL_BG,
            corner_radius=6,
        )
        self._status_banner.grid_columnconfigure(0, weight=1)

        self._status_seen_label = ctk.CTkLabel(
            self._status_banner,
            text="",
            font=("Segoe UI", 12, "bold"),
            text_color=_BANNER_PARTIAL_TEXT,
            anchor="w",
        )
        self._status_seen_label.grid(row=0, column=0, sticky="ew", padx=12, pady=6)

    def _build_metrics(self) -> None:
        """Build compact summary cards for the current system."""
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        for column in range(4):
            metrics.grid_columnconfigure(column, weight=1)

        self._build_metric(metrics, 0, "exams", "Exams in system")
        self._build_metric(metrics, 1, "days", "Exam days")
        self._build_metric(metrics, 2, "sections", "Semester / moed")
        self._build_metric(metrics, 3, "months", "Months shown")

    def _build_metric(
        self,
        master: ctk.CTkFrame,
        column: int,
        key: str,
        label: str,
    ) -> None:
        card = ctk.CTkFrame(
            master,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))

        ctk.CTkLabel(
            card,
            text=label,
            font=("Segoe UI", 10, "bold"),
            text_color=_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))

        value = ctk.CTkLabel(
            card,
            text="-",
            font=("Segoe UI", 19, "bold"),
            text_color=(_PRIMARY, "#93C5FD"),
            anchor="w",
        )
        value.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
        self._metric_labels[key] = value

    def _build_main_area(self) -> None:
        """Build calendar and details columns."""
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 12))
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        calendar_card = ctk.CTkFrame(
            main,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        calendar_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        calendar_card.grid_columnconfigure(0, weight=1)
        calendar_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            calendar_card,
            text="Calendar Review",
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 8))

        self._body = ctk.CTkScrollableFrame(
            calendar_card,
            fg_color=_SUBTLE_SURFACE,
            border_width=0,
            corner_radius=8,
        )
        self._body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self._body.grid_columnconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(main, fg_color="transparent")
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(0, weight=2)
        sidebar.grid_rowconfigure(1, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)

        details_card = ctk.CTkScrollableFrame(
            sidebar,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
            height=430,
        )
        details_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        details_card.grid_columnconfigure(0, weight=1)

        self._selected_day_label = ctk.CTkLabel(
            details_card,
            text="Selected Date",
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT,
            anchor="w",
        )
        self._selected_day_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))

        self._selected_day_hint = ctk.CTkLabel(
            details_card,
            text="Click a highlighted date to inspect its exams.",
            font=("Segoe UI", 11),
            text_color=_MUTED,
            anchor="w",
        )
        self._selected_day_hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._details_body = ctk.CTkFrame(
            details_card,
            fg_color=_SUBTLE_SURFACE,
            corner_radius=8,
        )
        self._details_body.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._details_body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            details_card,
            text="Full Schedule",
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))

        self._schedule_body = ctk.CTkFrame(
            details_card,
            fg_color="transparent",
        )
        self._schedule_body.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._schedule_body.grid_columnconfigure(0, weight=1)

        self._build_part4_tools_panel(sidebar)
        self._build_ranking_panel(sidebar)

    def _build_part4_tools_panel(self, sidebar: ctk.CTkFrame) -> None:
        """Build snapshot and manual-edit controls."""
        panel = ctk.CTkScrollableFrame(
            sidebar,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
            height=360,
        )
        panel.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="Part 4 Tools",
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            panel,
            text="Save versions, compare changes, and safely move one exam.",
            font=("Segoe UI", 11),
            text_color=_MUTED,
            anchor="w",
            wraplength=320,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        self._build_snapshot_controls(panel, start_row=2)
        self._build_manual_move_controls(panel, start_row=12)

    def _build_snapshot_controls(
        self,
        panel: ctk.CTkFrame,
        start_row: int,
    ) -> None:
        """Build snapshot save, load, delete, and compare controls."""
        ctk.CTkLabel(
            panel,
            text="Snapshots",
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=start_row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 4))

        self._snapshot_name_entry = ctk.CTkEntry(
            panel,
            placeholder_text="Snapshot name",
        )
        self._snapshot_name_entry.grid(
            row=start_row + 1,
            column=0,
            sticky="ew",
            padx=(16, 8),
            pady=(0, 8),
        )

        ctk.CTkButton(
            panel,
            text="Save",
            width=74,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_save_snapshot,
        ).grid(row=start_row + 1, column=1, sticky="e", padx=(0, 16), pady=(0, 8))

        self._snapshot_list_label = ctk.CTkLabel(
            panel,
            text="No saved snapshots.",
            font=("Segoe UI", 10),
            text_color=_MUTED,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._snapshot_list_label.grid(
            row=start_row + 2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )

        self._snapshot_first_selector = ctk.CTkOptionMenu(
            panel,
            values=[_EMPTY_OPTION],
            width=148,
            fg_color=_CONTROL_BG,
            button_color=_CONTROL_BUTTON,
            button_hover_color=_CONTROL_HOVER,
            text_color=_TEXT,
        )
        self._snapshot_first_selector.grid(
            row=start_row + 3,
            column=0,
            sticky="ew",
            padx=(16, 8),
            pady=(0, 8),
        )

        self._snapshot_second_selector = ctk.CTkOptionMenu(
            panel,
            values=[_EMPTY_OPTION],
            width=148,
            fg_color=_CONTROL_BG,
            button_color=_CONTROL_BUTTON,
            button_hover_color=_CONTROL_HOVER,
            text_color=_TEXT,
        )
        self._snapshot_second_selector.grid(
            row=start_row + 3,
            column=1,
            sticky="ew",
            padx=(0, 16),
            pady=(0, 8),
        )

        action_row = ctk.CTkFrame(panel, fg_color="transparent")
        action_row.grid(
            row=start_row + 4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        for column in range(3):
            action_row.grid_columnconfigure(column, weight=1)

        self._load_snapshot_button = ctk.CTkButton(
            action_row,
            text="Load",
            command=self._handle_load_snapshot,
        )
        self._load_snapshot_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._delete_snapshot_button = ctk.CTkButton(
            action_row,
            text="Delete",
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=(_ERROR, "#FCA5A5"),
            command=self._handle_delete_snapshot,
        )
        self._delete_snapshot_button.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self._compare_snapshot_button = ctk.CTkButton(
            action_row,
            text="Compare",
            command=self._handle_compare_snapshots,
        )
        self._compare_snapshot_button.grid(row=0, column=2, sticky="ew")

        compare_card = ctk.CTkFrame(
            panel,
            fg_color=_RESULT_CARD_BG,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        compare_card.grid(
            row=start_row + 5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        compare_card.grid_columnconfigure(0, weight=1)
        self._snapshot_compare_box = ctk.CTkLabel(
            compare_card,
            text="",
            font=("Segoe UI", 11),
            text_color=_TEXT,
            anchor="nw",
            justify="left",
            wraplength=300,
        )
        self._snapshot_compare_box.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=10,
        )
        self._write_textbox(
            self._snapshot_compare_box,
            "Comparison results will appear here.",
        )

        self._snapshot_status_label = ctk.CTkLabel(
            panel,
            text="",
            font=("Segoe UI", 10),
            text_color=_MUTED,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._snapshot_status_label.grid(
            row=start_row + 6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 10),
        )

    def _build_manual_move_controls(
        self,
        panel: ctk.CTkFrame,
        start_row: int,
    ) -> None:
        """Build safe manual-move and undo/redo controls."""
        ctk.CTkLabel(
            panel,
            text="Manual Move",
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=start_row, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 4))

        self._move_course_selector = ctk.CTkOptionMenu(
            panel,
            values=[_EMPTY_OPTION],
            width=320,
            fg_color=_CONTROL_BG,
            button_color=_CONTROL_BUTTON,
            button_hover_color=_CONTROL_HOVER,
            text_color=_TEXT,
            command=lambda _value: self._refresh_move_date_options(),
        )
        self._move_course_selector.grid(
            row=start_row + 1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )

        self._move_date_selector = ctk.CTkOptionMenu(
            panel,
            values=[_EMPTY_OPTION],
            width=148,
            fg_color=_CONTROL_BG,
            button_color=_CONTROL_BUTTON,
            button_hover_color=_CONTROL_HOVER,
            text_color=_TEXT,
        )
        self._move_date_selector.grid(
            row=start_row + 2,
            column=0,
            sticky="ew",
            padx=(16, 8),
            pady=(0, 8),
        )

        self._apply_move_button = ctk.CTkButton(
            panel,
            text="Apply Move",
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_apply_move,
        )
        self._apply_move_button.grid(
            row=start_row + 2,
            column=1,
            sticky="ew",
            padx=(0, 16),
            pady=(0, 8),
        )

        undo_row = ctk.CTkFrame(panel, fg_color="transparent")
        undo_row.grid(
            row=start_row + 3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        undo_row.grid_columnconfigure(0, weight=1)
        undo_row.grid_columnconfigure(1, weight=1)

        self._undo_move_button = ctk.CTkButton(
            undo_row,
            text="Undo",
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=(_PRIMARY, "#93C5FD"),
            command=self._handle_undo_move,
        )
        self._undo_move_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._redo_move_button = ctk.CTkButton(
            undo_row,
            text="Redo",
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=(_PRIMARY, "#93C5FD"),
            command=self._handle_redo_move,
        )
        self._redo_move_button.grid(row=0, column=1, sticky="ew")

        impact_card = ctk.CTkFrame(
            panel,
            fg_color=_RESULT_CARD_BG,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        impact_card.grid(
            row=start_row + 4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        impact_card.grid_columnconfigure(0, weight=1)
        self._move_impact_box = ctk.CTkLabel(
            impact_card,
            text="",
            font=("Segoe UI", 11),
            text_color=_TEXT,
            anchor="nw",
            justify="left",
            wraplength=300,
        )
        self._move_impact_box.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=10,
        )
        self._write_textbox(
            self._move_impact_box,
            "Move impact will appear here.",
        )

        self._move_status_label = ctk.CTkLabel(
            panel,
            text="",
            font=("Segoe UI", 10),
            text_color=_MUTED,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._move_status_label.grid(
            row=start_row + 5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 10),
        )

    def _build_ranking_panel(self, sidebar: ctk.CTkFrame) -> None:
        """Build ranking controls and current-system metric readout."""
        panel = ctk.CTkScrollableFrame(
            sidebar,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
            height=320,
        )
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Ranking",
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            panel,
            text=(
                "Choose ranking criteria. During generation this reorders only "
                "the temporary preview; final export is enabled after ranking completes."
            ),
            font=("Segoe UI", 11),
            text_color=_MUTED,
            anchor="w",
            wraplength=320,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        self._criterion_selector = ctk.CTkOptionMenu(
            panel,
            values=list(_RANKING_LABELS.values()),
            width=210,
            fg_color=_PRIMARY,
            button_color="#1E40AF",
            button_hover_color=_PRIMARY_HOVER,
        )
        self._criterion_selector.grid(row=2, column=0, sticky="ew", padx=(16, 8), pady=(0, 10))
        self._criterion_selector.set(_RANKING_LABELS[RankingCriterion.min_mandatory_gap])

        ctk.CTkButton(
            panel,
            text="Add",
            width=70,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_add_ranking_criterion,
        ).grid(row=2, column=1, sticky="e", padx=(0, 16), pady=(0, 10))

        self._ranking_rows_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self._ranking_rows_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12)
        self._ranking_rows_frame.grid_columnconfigure(0, weight=1)

        self._apply_ranking_button = ctk.CTkButton(
            panel,
            text="Apply Ranking",
            width=128,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_apply_ranking,
        )
        self._apply_ranking_button.grid(row=4, column=0, sticky="w", padx=16, pady=(10, 8))

        self._ranking_status_label = ctk.CTkLabel(
            panel,
            text="No ranking criteria selected.",
            font=("Segoe UI", 11),
            text_color=_MUTED,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._ranking_status_label.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))

        metrics = ctk.CTkFrame(panel, fg_color=_SUBTLE_SURFACE, corner_radius=8)
        metrics.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        metrics.grid_columnconfigure(1, weight=1)

        metric_rows = [
            ("min_mandatory_gap", "Min mandatory gap"),
            ("average_all_gap", "Average gap"),
            ("elective_collision_count", "Elective collisions"),
            ("mandatory_span", "Mandatory span"),
            ("max_exams_per_day", "Max exams/day"),
        ]
        for row_index, (key, label) in enumerate(metric_rows):
            ctk.CTkLabel(
                metrics,
                text=label,
                font=("Segoe UI", 10, "bold"),
                text_color=_MUTED,
                anchor="w",
            ).grid(row=row_index, column=0, sticky="w", padx=(12, 8), pady=(8 if row_index == 0 else 2, 2))

            value = ctk.CTkLabel(
                metrics,
                text="-",
                font=("Segoe UI", 11, "bold"),
                text_color=_TEXT,
                anchor="e",
            )
            value.grid(row=row_index, column=1, sticky="e", padx=(8, 12), pady=(8 if row_index == 0 else 2, 2))
            self._ranking_metric_labels[key] = value

        self._refresh_ranking_order()

    def _build_footer(self) -> None:
        """Build a small export/status footer."""
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            footer,
            text="",
            text_color=_MUTED,
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, sticky="ew")

    def _handle_next(self) -> None:
        """Advance to the next system and repaint the review."""
        self.presenter.next()
        self._refresh()

    def _handle_previous(self) -> None:
        """Go to the previous system and repaint the review."""
        self.presenter.previous()
        self._refresh()

    def _handle_save(self) -> None:
        """Ask for a destination file and export the currently shown system."""
        if getattr(getattr(self, "presenter", None), "is_partial", False) is True:
            self._status_label.configure(
                text=(
                    "Export is available after ranking completes. "
                    "The current Top 50 is still a temporary live preview."
                ),
                text_color="#B00020",
            )
            return

        chosen = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Save Exam Schedule",
            defaultextension=".txt",
            initialfile="exam_schedules.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        result = self._export_presenter.export_current(chosen or None)

        if result.status == ExportStatus.SUCCESS or result.success:
            color = "#2e7d32"
        elif result.status == ExportStatus.CANCELLED:
            color = "#666666"
        else:
            color = _ERROR
        self._status_label.configure(text=result.message, text_color=color)

    def _handle_save_snapshot(self) -> None:
        """Save the current schedule snapshot from the sidebar."""
        name = self._snapshot_name_entry.get() if self._snapshot_name_entry else ""
        result = self.presenter.save_snapshot(name)
        self._set_snapshot_status(result.message, result.success)
        if result.success and self._snapshot_name_entry is not None:
            self._snapshot_name_entry.delete(0, "end")
        self._refresh_part4_controls()

    def _handle_load_snapshot(self) -> None:
        """Load the selected snapshot into the current review slot."""
        result = self.presenter.load_snapshot(self._selected_snapshot_name())
        self._set_snapshot_status(result.message, result.success)
        if result.success:
            self._reset_calendar_grid()
            self._refresh()

    def _handle_delete_snapshot(self) -> None:
        """Delete the selected snapshot."""
        result = self.presenter.delete_snapshot(self._selected_snapshot_name())
        self._set_snapshot_status(result.message, result.success)
        self._refresh_part4_controls()

    def _handle_compare_snapshots(self) -> None:
        """Compare the two selected snapshots."""
        first = self._selected_snapshot_name(self._snapshot_first_selector)
        second = self._selected_snapshot_name(self._snapshot_second_selector)
        result = self.presenter.compare_snapshots(first, second)
        self._set_snapshot_status(result.message, result.success)
        if result.details:
            self._write_textbox(self._snapshot_compare_box, result.details)

    def _handle_apply_move(self) -> None:
        """Apply a safe manual move through the presenter."""
        course = self._selected_option(self._move_course_selector)
        target_date = self._selected_option(self._move_date_selector)
        result = self.presenter.apply_manual_move(course, target_date)
        self._set_move_status(result.message, result.success)
        if result.details:
            self._write_textbox(self._move_impact_box, result.details)
        if result.success:
            self._reset_calendar_grid()
            self._refresh()
        else:
            self._refresh_part4_controls()

    def _handle_undo_move(self) -> None:
        """Undo the latest manual move."""
        result = self.presenter.undo_manual_move()
        self._set_move_status(result.message, result.success)
        if result.success:
            self._write_textbox(self._move_impact_box, "Manual move was undone.")
            self._reset_calendar_grid()
            self._refresh()
        else:
            self._refresh_part4_controls()

    def _handle_redo_move(self) -> None:
        """Redo the latest undone manual move."""
        result = self.presenter.redo_manual_move()
        self._set_move_status(result.message, result.success)
        if result.success:
            self._write_textbox(self._move_impact_box, "Manual move was redone.")
            self._reset_calendar_grid()
            self._refresh()
        else:
            self._refresh_part4_controls()

    def _handle_theme_toggle(self) -> None:
        """Switch between light and dark mode."""
        handle_theme_toggle(
            self._on_theme_toggle,
            self._theme_button,
            self._theme_button_text,
        )

    def _handle_add_ranking_criterion(self) -> None:
        """Add the selected criterion unless it is already active."""
        criterion = self._selected_ranking_criterion()
        if criterion in self._ranking_criteria:
            self._set_ranking_status("This criterion is already active.", ok=False)
            return

        self._ranking_criteria.append(criterion)
        self._refresh_ranking_order()
        self._set_ranking_status("Ranking criterion added.", ok=None)

    def _handle_remove_ranking_criterion(
        self,
        criterion: RankingCriterion,
    ) -> None:
        """Remove one active ranking criterion."""
        self._ranking_criteria = [
            active
            for active in self._ranking_criteria
            if active != criterion
        ]
        self._refresh_ranking_order()
        self._set_ranking_status("Ranking criterion removed.", ok=None)

    def _handle_move_ranking_criterion(
        self,
        criterion: RankingCriterion,
        direction: int,
    ) -> None:
        """Move a criterion up or down in priority order."""
        try:
            index = self._ranking_criteria.index(criterion)
        except ValueError:
            return

        new_index = index + direction
        if new_index < 0 or new_index >= len(self._ranking_criteria):
            return

        self._ranking_criteria[index], self._ranking_criteria[new_index] = (
            self._ranking_criteria[new_index],
            self._ranking_criteria[index],
        )
        self._refresh_ranking_order()
        self._set_ranking_status("Ranking order updated.", ok=None)

    def _handle_apply_ranking(self) -> None:
        """Apply ranking in the background and stream a bounded preview."""
        settings = self._ranking_settings()

        if not settings.priority_list:
            if getattr(self._ranking_runner, "is_running", False):
                self._ranking_runner.cancel_current()
                self._ranking_runner = AsyncScheduleRunner()
            self._ranking_run_id = getattr(self, "_ranking_run_id", 0) + 1
            result = self.presenter.apply_ranking(settings)
            self._set_ranking_status(result.message, ok=result.success)
            if result.success:
                self._reset_calendar_grid()
                self._refresh()
            return

        self._ranking_run_id = getattr(self, "_ranking_run_id", 0) + 1
        run_id = self._ranking_run_id

        if getattr(self._ranking_runner, "is_running", False):
            self._ranking_runner.cancel_current()
            self._ranking_runner = AsyncScheduleRunner()

        def task(token, on_progress):
            return self.presenter.rank_progressively(
                settings,
                run_id=run_id,
                on_update=on_progress,
                cancellation_token=token,
                batch_size=1000,
                preview_limit=50,
                min_update_interval_seconds=0.35,
            )

        accepted = self._ranking_runner.run_with_progress(
            task=task,
            on_started=lambda: self._on_ranking_started(run_id),
            on_progress=lambda update: self.after(
                0,
                lambda item=update: self._handle_ranking_update(item),
            ),
            on_complete=lambda update: self.after(
                0,
                lambda item=update: self._handle_ranking_complete(
                    run_id,
                    item,
                ),
            ),
            on_error=lambda error: self.after(
                0,
                lambda exc=error: self._handle_ranking_error(run_id, exc),
            ),
        )

        if not accepted:
            self._set_ranking_status("Ranking is already running.", ok=False)

    def _on_ranking_started(self, run_id: int) -> None:
        """Show immediate feedback while the first ranked preview is computed."""
        if run_id != self._ranking_run_id:
            return
        self._set_ranking_status(
            "Ranking started. Live Top 50 preview will appear shortly.",
            ok=None,
        )
        if getattr(self, "_apply_ranking_button", None) is not None:
            self._apply_ranking_button.configure(text="Restart Ranking")

    def _handle_ranking_update(
        self,
        update: ProgressiveRankingUpdate,
    ) -> None:
        """Apply one live ranked preview update from the active worker."""
        if update.run_id != self._ranking_run_id:
            return
        self.push_live_update(
            update.ranked_schedules,
            is_partial=update.is_partial,
            systems_seen=update.processed_count,
        )
        self._set_ranking_status(update.message, ok=None)

    def _handle_ranking_complete(
        self,
        run_id: int,
        update: ProgressiveRankingUpdate,
    ) -> None:
        """Switch to final ranked Top 50 after the active worker finishes."""
        if run_id != self._ranking_run_id or update.run_id != self._ranking_run_id:
            return
        self.push_live_update(
            update.ranked_schedules,
            is_partial=False,
            systems_seen=update.total_count,
        )
        self._set_ranking_status(update.message, ok=True)
        if getattr(self, "_apply_ranking_button", None) is not None:
            self._apply_ranking_button.configure(text="Apply Ranking")

    def _handle_ranking_error(self, run_id: int, error: Exception) -> None:
        """Show ranking failures without letting stale workers repaint state."""
        if run_id != self._ranking_run_id:
            return
        self._set_ranking_status(
            f"Ranking failed unexpectedly: {type(error).__name__}.",
            ok=False,
        )
        if getattr(self, "_apply_ranking_button", None) is not None:
            self._apply_ranking_button.configure(text="Apply Ranking")

    def _reset_calendar_grid(self) -> None:
        """Force the calendar grid to rebuild for a changed schedule order."""
        body = getattr(self, "_body", None)
        if body is not None:
            for child in body.winfo_children():
                child.destroy()
        self._exam_cells = {}
        self._built_months = set()
        self._selected_iso_date = None
        self._grid_built = False

    def push_live_error(self, error_message: str) -> None:
        """Display a fatal generation error in the status banner.

        MUST be called on the main (Tkinter) thread. Shows the banner with a
        red tint and a ❌ icon so the user immediately sees that generation
        failed.

        Args:
            error_message: Human-readable description of the error.
        """
        self._status_banner.configure(
            fg_color=("#FEE2E2", "#5A1F1F"),
        )
        self._status_seen_label.configure(
            text=f"❌  {error_message}",
            text_color=("#991B1B", "#FCA5A5"),
        )
        if not self._status_banner.winfo_ismapped():
            self._status_banner.grid(
                row=2, column=0, columnspan=2, sticky="ew", pady=(6, 2)
            )

    def push_live_update(
        self,
        schedules: list,
        is_partial: bool,
        systems_seen: int,
    ) -> None:
        """Public hook for the background generator to push live batches.

        MUST be called on the main (Tkinter) thread, for example:
        ``root.after(0, lambda: screen.push_live_update(...))``.

        Incremental calendar rendering means only new month cards are appended
        to the DOM; no full grid rebuild occurs unless the grid has been
        invalidated, for example after Apply Ranking.

        Args:
            schedules: The full list of systems available so far.
            is_partial: True while generation is still running.
            systems_seen: Total systems produced by the generator so far.
        """
        displayed_count = len(schedules)
        self.presenter.update_schedules(
            schedules,
            is_partial=is_partial,
            systems_seen=systems_seen,
            displayed_count=displayed_count,
        )
        self._update_status_banner(is_partial, systems_seen, displayed_count)

        if self.presenter.has_schedules():
            self._build_relevant_months_grid()
            self._grid_built = True

        self._refresh()

    def _update_status_banner(
        self,
        is_partial: bool,
        systems_seen: int,
        displayed_count: int,
    ) -> None:
        """Paint the status banner with the correct colour and copy."""
        mode = getattr(self.presenter, "result_mode", None)
        if isinstance(mode, str):
            try:
                mode = ResultMode(mode)
            except ValueError:
                mode = None

        if not is_partial and mode != ResultMode.FINAL_RANKED:
            if self._status_banner.winfo_ismapped():
                self._status_banner.grid_forget()
            return

        if is_partial:
            bg = _BANNER_PARTIAL_BG
            text_color = _BANNER_PARTIAL_TEXT
            icon = "⏳"
            msg = (
                f"{icon}  Live preview: showing temporary Top {displayed_count:,} "
                f"from {systems_seen:,} ranked so far."
            )
        else:
            bg = _BANNER_FINAL_BG
            text_color = _BANNER_FINAL_TEXT
            icon = "✅"
            if displayed_count == systems_seen:
                msg = (
                    f"{icon}  Ranking complete. Showing "
                    f"{displayed_count:,} ranked schedules."
                )
            else:
                msg = (
                    f"{icon}  Final Top {displayed_count:,} ranking complete. Showing "
                    f"{displayed_count:,} of {systems_seen:,} ranked schedules."
                )
        self._status_banner.configure(fg_color=bg)
        self._status_seen_label.configure(text=msg, text_color=text_color)

        if not self._status_banner.winfo_ismapped():
            self._status_banner.grid(
                row=2, column=0, columnspan=2, sticky="ew", pady=(6, 2)
            )

    def _refresh(self) -> None:
        """Refresh counter, metrics, calendar highlights, and detail panes."""
        view = self.presenter.current_view()
        if view is None:
            # Some unit tests and legacy callers provide a presenter test-double
            # without this property. MagicMock attributes are truthy by default,
            # so only an explicit True should switch to the live-generation copy.
            is_partial = getattr(self.presenter, "is_partial", False) is True
            if is_partial:
                empty_text = "Generating schedules… No preview available yet."
            else:
                empty_text = "No schedules to display."

            self._counter_label.configure(text=empty_text)
            self._prev_button.configure(state="disabled")
            self._next_button.configure(state="disabled")
            if self._save_button is not None:
                self._save_button.configure(state="disabled")

            # Ranking controls remain enabled even during partial generation so
            # the user can apply ranking at any time.
            self._refresh_ranking_metrics(None)
            self._refresh_part4_controls()
            return

        if not self._grid_built:
            for child in self._body.winfo_children():
                child.destroy()
            self._exam_cells = {}
            self._built_months = set()
            self._build_relevant_months_grid()
            self._grid_built = True

        self._current_exams_by_iso_date = view.exams_by_iso_date
        self._current_day_status_by_iso_date = view.day_status_by_iso_date
        if self._selected_iso_date not in self._current_exams_by_iso_date:
            self._selected_iso_date = self._first_exam_date()

        self._counter_label.configure(
            text=f"System {view.position} of {view.total}"
        )
        mode = getattr(self.presenter, "result_mode", None)
        if isinstance(mode, str):
            try:
                mode = ResultMode(mode)
            except ValueError:
                mode = None
        should_show_banner = (
            getattr(self.presenter, "is_partial", False) is True
            or mode == ResultMode.FINAL_RANKED
        )
        if self._status_banner.winfo_ismapped() and not should_show_banner:
            self._status_banner.grid_forget()
        if should_show_banner and not self._status_banner.winfo_ismapped():
            raw_systems_seen = getattr(self.presenter, "systems_seen", 0)
            raw_displayed_count = getattr(self.presenter, "displayed_count", 0)
            systems_seen = (
                raw_systems_seen
                if isinstance(raw_systems_seen, int) and raw_systems_seen > 0
                else view.total
            )
            displayed_count = (
                raw_displayed_count
                if isinstance(raw_displayed_count, int) and raw_displayed_count > 0
                else view.total
            )
            self._update_status_banner(
                getattr(self.presenter, "is_partial", False) is True,
                systems_seen,
                displayed_count,
            )
        self._refresh_metrics(view)
        self._paint_exam_days(view.exams_by_iso_date)
        self._render_selected_day()
        self._render_system_exam_list(view.sections)
        self._refresh_ranking_metrics(view.metrics_summary)
        self._refresh_part4_controls(view)

        self._prev_button.configure(
            state="normal" if self.presenter.can_go_previous() else "disabled"
        )
        self._next_button.configure(
            state="normal" if self.presenter.can_go_next() else "disabled"
        )
        if self._save_button is not None:
            self._save_button.configure(
                state=(
                    "disabled"
                    if getattr(self.presenter, "is_partial", False) is True
                    else "normal"
                )
            )
        if getattr(self, "_apply_ranking_button", None) is not None:
            self._apply_ranking_button.configure(state="normal")

    def _refresh_metrics(self, view) -> None:
        """Update summary cards from the current system view."""
        exam_count = sum(len(section.exams) for section in view.sections)
        self._metric_labels["exams"].configure(text=str(exam_count))
        self._metric_labels["days"].configure(text=str(len(view.exams_by_iso_date)))
        self._metric_labels["sections"].configure(text=str(len(view.sections)))
        self._metric_labels["months"].configure(text=str(len(self.presenter.relevant_months())))

    def _refresh_ranking_order(self) -> None:
        """Render the active ranking priority list."""
        if self._ranking_rows_frame is None:
            return

        for child in self._ranking_rows_frame.winfo_children():
            child.destroy()

        if not self._ranking_criteria:
            ctk.CTkLabel(
                self._ranking_rows_frame,
                text="No active ranking criteria.",
                font=("Segoe UI", 11),
                text_color=_MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=4, pady=4)
            return

        for row_index, criterion in enumerate(self._ranking_criteria):
            row = ctk.CTkFrame(
                self._ranking_rows_frame,
                fg_color=_SUBTLE_SURFACE,
                corner_radius=8,
            )
            row.grid(row=row_index, column=0, sticky="ew", padx=0, pady=(4, 0))
            row.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                row,
                text=f"{row_index + 1}. {_RANKING_LABELS[criterion]}",
                font=("Segoe UI", 11, "bold"),
                text_color=_TEXT,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=8)

            ctk.CTkButton(
                row,
                text="Up",
                width=42,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                command=lambda item=criterion: self._handle_move_ranking_criterion(
                    item,
                    -1,
                ),
            ).grid(row=0, column=1, padx=(0, 4), pady=6)

            ctk.CTkButton(
                row,
                text="Down",
                width=54,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                command=lambda item=criterion: self._handle_move_ranking_criterion(
                    item,
                    1,
                ),
            ).grid(row=0, column=2, padx=(0, 4), pady=6)

            ctk.CTkButton(
                row,
                text="Remove",
                width=68,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=("#B00020", "#FCA5A5"),
                command=lambda item=criterion: self._handle_remove_ranking_criterion(
                    item
                ),
            ).grid(row=0, column=3, padx=(0, 8), pady=6)

    def _refresh_ranking_metrics(self, metrics) -> None:
        """Display current-system ranking metrics when available."""
        if not getattr(self, "_ranking_metric_labels", None):
            return

        if metrics is None:
            for label in self._ranking_metric_labels.values():
                label.configure(text="-")
            return

        values = {
            "min_mandatory_gap": str(metrics.min_mandatory_gap),
            "average_all_gap": f"{metrics.average_all_gap:.2f}",
            "elective_collision_count": str(metrics.elective_collision_count),
            "mandatory_span": str(metrics.mandatory_span),
            "max_exams_per_day": str(metrics.max_exams_per_day),
        }
        for key, value in values.items():
            self._ranking_metric_labels[key].configure(text=value)

    def _set_ranking_status(
        self,
        message: str,
        ok: bool | None,
    ) -> None:
        if self._ranking_status_label is None:
            return

        if ok is True:
            color = "#2e7d32"
        elif ok is False:
            color = "#B00020"
        else:
            color = _MUTED

        self._ranking_status_label.configure(text=message, text_color=color)

    def _selected_ranking_criterion(self) -> RankingCriterion:
        selected = self._criterion_selector.get()
        for criterion, label in _RANKING_LABELS.items():
            if label == selected:
                return criterion
        return RankingCriterion.min_mandatory_gap

    def _ranking_settings(self) -> RankingSettings:
        return RankingSettings(
            [
                RankingPreference(
                    criterion=criterion,
                    descending=True,
                )
                for criterion in self._ranking_criteria
            ]
        )

    def _build_relevant_months_grid(self) -> None:
        """Incrementally draw only months that contain exams in any system.

        On the first call, or after a full grid reset, every relevant month is
        appended. On later calls from ``push_live_update`` only months not yet
        present in ``_built_months`` are appended, avoiding a full Tkinter DOM
        rebuild on every live batch.
        """
        for year, month in self.presenter.relevant_months():
            if (year, month) in self._built_months:
                continue
            self._build_month(year, month)
            self._built_months.add((year, month))

    def _build_month(self, year: int, month: int) -> None:
        """Create one compact month card."""
        month_frame = ctk.CTkFrame(
            self._body,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        month_frame.pack(fill="x", padx=6, pady=(6, 10))
        for col in range(7):
            month_frame.grid_columnconfigure(col, weight=1, uniform="day")

        ctk.CTkLabel(
            month_frame,
            text=f"{_MONTH_NAMES[month - 1]} {year}",
            font=("Segoe UI", 14, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, columnspan=7, sticky="w", padx=12, pady=(10, 6))

        for col, label in enumerate(_WEEKDAY_HEADERS):
            ctk.CTkLabel(
                month_frame,
                text=label,
                font=("Segoe UI", 10, "bold"),
                text_color=_MUTED,
            ).grid(row=1, column=col, padx=2, pady=2)

        for week_index, week in enumerate(calendar.monthcalendar(year, month)):
            for col, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(month_frame, text="").grid(
                        row=2 + week_index,
                        column=col,
                        padx=3,
                        pady=3,
                        sticky="nsew",
                    )
                    continue
                self._build_day_cell(month_frame, 2 + week_index, col, year, month, day)

    def _build_day_cell(
        self,
        parent: ctk.CTkFrame,
        row: int,
        col: int,
        year: int,
        month: int,
        day: int,
    ) -> None:
        """Create one calendar day cell."""
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        cell = ctk.CTkButton(
            parent,
            text=str(day),
            height=30,
            fg_color="transparent",
            hover=False,
            text_color=_REGULAR_DAY_TEXT,
            command=lambda: None,
            state="disabled",
            corner_radius=7,
        )
        cell.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
        self._exam_cells[iso] = cell

    def _paint_exam_days(
        self,
        exams_by_iso_date: dict[str, list[ExamRow]],
    ) -> None:
        """Highlight only exam days for the current system."""
        for iso_date, cell in self._exam_cells.items():
            cell.configure(
                text=str(int(iso_date[-2:])),
                fg_color="transparent",
                hover=False,
                text_color=_REGULAR_DAY_TEXT,
                border_width=0,
                command=lambda: None,
                state="disabled",
            )

            exams = exams_by_iso_date.get(iso_date)
            if not exams:
                continue

            selected = iso_date == getattr(self, "_selected_iso_date", None)
            day_status = getattr(
                self,
                "_current_day_status_by_iso_date",
                {},
            ).get(iso_date)
            style = self._day_cell_style(day_status, selected)
            cell.configure(
                text=self._day_cell_text(iso_date, exams, day_status),
                fg_color=style["fg_color"],
                hover=True,
                hover_color=style["hover_color"],
                text_color=style["text_color"],
                border_width=style["border_width"],
                border_color=style["border_color"],
                command=lambda d=iso_date, rows=exams: self._handle_exam_day_click(
                    d,
                    rows,
                ),
                state="normal",
            )

    def _handle_exam_day_click(
        self,
        iso_date: str,
        exams: list[ExamRow],
    ) -> None:
        """Handle an exam-day click in full UI or headless compatibility mode."""
        if hasattr(self, "_details_body"):
            self._select_day(iso_date)
            return

        self._show_day_popup(iso_date, exams)

    def _select_day(self, iso_date: str) -> None:
        """Select a day and refresh the detail panel."""
        self._selected_iso_date = iso_date
        self._paint_exam_days(self._current_exams_by_iso_date)
        self._render_selected_day()

    def _show_day_popup(
        self,
        iso_date: str,
        exams: list[ExamRow],
    ) -> None:
        """Legacy popup used by older headless tests and fallback UI paths."""
        popup = ctk.CTkToplevel(self.winfo_toplevel())
        popup.title(f"Exams on {iso_date}")
        popup.geometry("460x320")
        popup.transient(self.winfo_toplevel())
        popup.grab_set()

        body = ctk.CTkFrame(popup, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            body,
            text=f"Exams scheduled on {iso_date}",
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT,
        ).pack(anchor="w", pady=(0, 10))

        for exam in exams:
            ctk.CTkLabel(
                body,
                text=f"{exam.course_number}  -  {exam.course_name}",
                font=("Segoe UI", 13, "bold"),
                text_color=_TEXT,
                anchor="w",
            ).pack(anchor="w", pady=(6, 2))

            ctk.CTkLabel(
                body,
                text=(
                    f"Type: {self._format_exam_type(exam.status)}    "
                    f"Programs: {exam.program_numbers}    "
                    f"Date: {exam.exam_date}"
                ),
                font=("Segoe UI", 11),
                text_color=_MUTED,
                anchor="w",
            ).pack(anchor="w")

    def _render_selected_day(self) -> None:
        """Show selected-day exam details in the sidebar."""
        for child in self._details_body.winfo_children():
            child.destroy()

        if self._selected_iso_date is None:
            self._selected_day_label.configure(text="Selected Date")
            self._selected_day_hint.configure(text="Click a highlighted date to inspect its exams.")
            return

        exams = self._current_exams_by_iso_date.get(self._selected_iso_date, [])
        day_status = self._current_day_status_by_iso_date.get(self._selected_iso_date)
        self._selected_day_label.configure(
            text=f"Selected date: {self._format_iso_date(self._selected_iso_date)}"
        )
        if day_status is not None:
            hint = (
                f"{day_status.label}: {len(exams)} exam"
                f"{'s' if len(exams) != 1 else ''}. {day_status.details}"
            )
        else:
            hint = (
                f"{len(exams)} exam{'s' if len(exams) != 1 else ''} "
                "scheduled on this date."
            )
        self._selected_day_hint.configure(
            text=hint
        )

        for row_index, exam in enumerate(exams):
            self._build_exam_detail_card(self._details_body, row_index, exam)

    def _render_system_exam_list(self, sections) -> None:
        """Render the full current system as compact grouped rows."""
        for child in self._schedule_body.winfo_children():
            child.destroy()

        row = 0
        for section in sections:
            ctk.CTkLabel(
                self._schedule_body,
                text=f"{section.semester} | {section.moed}",
                font=("Segoe UI", 11, "bold"),
                text_color=_MUTED,
                anchor="w",
            ).grid(row=row, column=0, sticky="ew", padx=4, pady=(6, 2))
            row += 1

            for exam in section.exams:
                ctk.CTkLabel(
                    self._schedule_body,
                    text=(
                        f"{exam.course_number} - {exam.course_name}\n"
                        f"Type: {self._format_exam_type(exam.status)} | "
                        f"Programs: {exam.program_numbers} | "
                        f"Date: {exam.exam_date}"
                    ),
                    font=("Segoe UI", 11),
                    text_color=_TEXT,
                    anchor="w",
                    justify="left",
                    wraplength=320,
                ).grid(row=row, column=0, sticky="ew", padx=12, pady=1)
                row += 1

    def _build_exam_detail_card(
        self,
        master: ctk.CTkFrame,
        row_index: int,
        exam: ExamRow,
    ) -> None:
        """Render one selected-day exam detail card."""
        card = ctk.CTkFrame(
            master,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        card.grid(row=row_index, column=0, sticky="ew", padx=4, pady=(4, 8))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=f"{exam.course_number} - {exam.course_name}",
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT,
            anchor="w",
            wraplength=320,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            card,
            text=(
                f"Type: {self._format_exam_type(exam.status)}\n"
                f"{self._lecturer_line(exam)}"
                f"Programs: {exam.program_numbers}\n"
                f"Date: {exam.exam_date}"
            ),
            font=("Segoe UI", 11),
            text_color=_MUTED,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

    def _refresh_part4_controls(self, view=None) -> None:
        """Refresh snapshot and manual-edit controls."""
        self._refresh_snapshot_controls()
        self._refresh_manual_move_controls(view)

    def _refresh_snapshot_controls(self) -> None:
        """Refresh snapshot dropdowns and saved-list text."""
        snapshot_summaries = getattr(self.presenter, "snapshot_summaries", None)
        if snapshot_summaries is None:
            return

        summaries = snapshot_summaries()
        names = [summary.name for summary in summaries]

        self._set_option_values(getattr(self, "_snapshot_first_selector", None), names)
        self._set_option_values(getattr(self, "_snapshot_second_selector", None), names)

        snapshot_list_label = getattr(self, "_snapshot_list_label", None)
        if snapshot_list_label is not None:
            snapshot_list_label.configure(
                text=self._snapshot_list_text(summaries),
            )

        has_snapshots = bool(names)
        self._set_button_state(getattr(self, "_load_snapshot_button", None), has_snapshots)
        self._set_button_state(getattr(self, "_delete_snapshot_button", None), has_snapshots)
        self._set_button_state(
            getattr(self, "_compare_snapshot_button", None),
            len(names) >= 2,
        )

    def _refresh_manual_move_controls(self, _view=None) -> None:
        """Refresh course/date selectors and undo button states."""
        course_options_getter = getattr(
            self.presenter,
            "manual_move_course_options",
            None,
        )
        if course_options_getter is None:
            return

        course_options = course_options_getter()
        self._set_option_values(getattr(self, "_move_course_selector", None), course_options)
        date_options = self._refresh_move_date_options()

        self._set_button_state(
            getattr(self, "_apply_move_button", None),
            bool(course_options and date_options),
        )

        undo_button = getattr(self, "_undo_move_button", None)
        if undo_button is not None:
            undo_button.configure(
                state=(
                    "normal"
                    if getattr(self.presenter, "can_undo_manual_move", False)
                    else "disabled"
                )
            )
        redo_button = getattr(self, "_redo_move_button", None)
        if redo_button is not None:
            redo_button.configure(
                state=(
                    "normal"
                    if getattr(self.presenter, "can_redo_manual_move", False)
                    else "disabled"
                )
            )

    def _refresh_move_date_options(self) -> list[str]:
        """Refresh target dates after the selected course changes."""
        date_options_getter = getattr(
            self.presenter,
            "manual_move_date_options",
            None,
        )
        if date_options_getter is None:
            return []

        course = self._selected_option(getattr(self, "_move_course_selector", None))
        date_options = date_options_getter(course)
        self._set_option_values(getattr(self, "_move_date_selector", None), date_options)
        return date_options

    @staticmethod
    def _set_option_values(option, values: list[str]) -> None:
        """Replace option-menu values while keeping a valid selection."""
        if option is None:
            return

        current = option.get()
        display_values = values or [_EMPTY_OPTION]
        option.configure(values=display_values)
        option.set(current if current in display_values else display_values[0])
        option.configure(state="normal" if values else "disabled")

    @staticmethod
    def _set_button_state(button, is_enabled: bool) -> None:
        """Enable or disable a button when it exists."""
        if button is not None:
            button.configure(state="normal" if is_enabled else "disabled")

    @staticmethod
    def _selected_option(option) -> str:
        """Return the selected option-menu value or an empty string."""
        if option is None:
            return ""
        value = option.get()
        return "" if value == _EMPTY_OPTION else value

    def _selected_snapshot_name(self, selector=None) -> str:
        """Return the selected snapshot name."""
        return self._selected_option(selector or self._snapshot_first_selector)

    def _set_snapshot_status(self, message: str, success: bool) -> None:
        """Show a snapshot action result."""
        if self._snapshot_status_label is not None:
            self._snapshot_status_label.configure(
                text=message,
                text_color=_SUCCESS if success else _ERROR,
            )
        if not success:
            self._show_user_message("Snapshot action needs attention", message)

    def _set_move_status(self, message: str, success: bool) -> None:
        """Show a manual-move action result."""
        if self._move_status_label is not None:
            self._move_status_label.configure(
                text=message,
                text_color=_SUCCESS if success else _ERROR,
            )
        if not success:
            self._show_user_message("Manual move needs attention", message)

    def _show_user_message(
        self,
        title: str,
        message: str,
        kind: str = "error",
    ) -> None:
        """Show an important message in a small modal window."""
        if not message:
            return
        try:
            parent = self.winfo_toplevel()
        except (AttributeError, RuntimeError, TypeError):
            return

        accent = _ERROR if kind == "error" else _INFO
        popup = ctk.CTkToplevel(parent)
        popup.title(title)
        popup.geometry(
            self._centered_popup_geometry(
                parent,
                _MESSAGE_POPUP_WIDTH,
                _MESSAGE_POPUP_HEIGHT,
            )
        )
        popup.transient(parent)
        popup.grab_set()
        if hasattr(popup, "resizable"):
            popup.resizable(False, False)
        if hasattr(popup, "configure"):
            popup.configure(fg_color=_PAGE_BG)

        body = ctk.CTkFrame(
            popup,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=10,
        )
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            body,
            text="!",
            width=30,
            height=30,
            fg_color=accent,
            corner_radius=15,
            font=("Segoe UI", 16, "bold"),
            text_color="#FFFFFF",
        ).grid(row=0, column=0, padx=(12, 10), pady=(12, 0), sticky="n")

        ctk.CTkLabel(
            body,
            text=title,
            font=("Segoe UI", 15, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 2))

        ctk.CTkLabel(
            body,
            text=message,
            font=("Segoe UI", 12),
            text_color=_MUTED,
            wraplength=330,
            justify="left",
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 12))

        ctk.CTkButton(
            body,
            text="OK",
            width=86,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=popup.destroy,
        ).grid(row=2, column=1, sticky="e", padx=(0, 12), pady=(0, 12))

    @staticmethod
    def _centered_popup_geometry(parent, width: int, height: int) -> str:
        """Return a geometry string that centers a modal over the app."""
        try:
            if hasattr(parent, "update_idletasks"):
                parent.update_idletasks()
            parent_width = int(parent.winfo_width())
            parent_height = int(parent.winfo_height())
            parent_x = int(parent.winfo_rootx())
            parent_y = int(parent.winfo_rooty())
            if parent_width > 1 and parent_height > 1:
                x = parent_x + (parent_width - width) // 2
                y = parent_y + (parent_height - height) // 2
                return f"{width}x{height}+{max(x, 0)}+{max(y, 0)}"
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        try:
            screen_width = int(parent.winfo_screenwidth())
            screen_height = int(parent.winfo_screenheight())
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            return f"{width}x{height}+{max(x, 0)}+{max(y, 0)}"
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return f"{width}x{height}"

    @staticmethod
    def _write_textbox(textbox, text: str) -> None:
        """Replace the text inside a result panel or legacy textbox."""
        if textbox is None:
            return
        if "text" in getattr(textbox, "options", {}):
            textbox.configure(text=text)
            if hasattr(textbox, "content"):
                textbox.content = text
            return
        if not (hasattr(textbox, "delete") and hasattr(textbox, "insert")):
            textbox.configure(text=text)
            return
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    @staticmethod
    def _snapshot_list_text(summaries) -> str:
        """Build the compact saved-snapshots list."""
        if not summaries:
            return "No saved snapshots."

        return "\n".join(
            f"{summary.name} | {summary.quality_tag} | {summary.created_at}"
            for summary in summaries
        )

    @staticmethod
    def _day_cell_text(
        iso_date: str,
        exams: list[ExamRow],
        day_status: DayStatusView | None,
    ) -> str:
        """Return compact text for one calendar cell."""
        prefix = ""
        if day_status is not None:
            if day_status.status == "conflict":
                prefix = "!! "
            elif day_status.status == "overloaded":
                prefix = "! "
        return f"{prefix}{int(iso_date[-2:])}  ({len(exams)})"

    @staticmethod
    def _day_cell_style(
        day_status: DayStatusView | None,
        selected: bool,
    ) -> dict:
        """Return colors for one calendar day status."""
        if day_status is None or day_status.status == "normal":
            return {
                "fg_color": _SELECTED_DAY_COLOR if selected else _EXAM_DAY_COLOR,
                "hover_color": _EXAM_DAY_HOVER,
                "text_color": _SELECTED_DAY_TEXT if selected else _EXAM_DAY_TEXT,
                "border_width": 2 if selected else 0,
                "border_color": _PRIMARY,
            }

        if day_status.status == "conflict":
            fg_color = _CONFLICT_DAY_COLOR
            text_color = _CONFLICT_DAY_TEXT
        elif day_status.status == "overloaded":
            fg_color = _OVERLOADED_DAY_COLOR
            text_color = _OVERLOADED_DAY_TEXT
        else:
            fg_color = _BUSY_DAY_COLOR
            text_color = _BUSY_DAY_TEXT

        return {
            "fg_color": fg_color,
            "hover_color": fg_color,
            "text_color": text_color,
            "border_width": 2 if selected else 1,
            "border_color": _PRIMARY if selected else _BORDER,
        }

    def _first_exam_date(self) -> str | None:
        """Return the first exam date in the current system."""
        if not self._current_exams_by_iso_date:
            return None
        return sorted(self._current_exams_by_iso_date)[0]

    @staticmethod
    def _format_iso_date(iso_date: str) -> str:
        """Format YYYY-MM-DD as DD-MM-YYYY for display."""
        year, month, day = iso_date.split("-")
        return f"{day}-{month}-{year}"

    @staticmethod
    def _format_exam_type(status: str) -> str:
        """Translate stored course status into user-facing requirement text."""
        normalized = status.strip().lower()
        if normalized == "obligatory":
            return "Mandatory"
        if normalized == "elective":
            return "Elective"
        return status or "Unknown"

    @staticmethod
    def _lecturer_line(exam: ExamRow) -> str:
        """Return a lecturer line only when lecturer data exists."""
        lecturer = exam.instructor.strip()
        if not lecturer:
            return ""
        return f"Lecturer: {lecturer}\n"
