"""Output screen: review and export generated exam schedules.

The screen keeps the existing passive MVP boundary: navigation state and
display models come from ``ScheduleNavigationPresenter`` while the view owns
layout, buttons, and file dialogs.
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

from gui.exportPresenter import ExportPresenter
from gui.scheduleNavigationPresenter import ExamRow, ScheduleNavigationPresenter


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
_EXAM_DAY_COLOR = ("#DBEAFE", "#1E3A8A")
_EXAM_DAY_HOVER = ("#BFDBFE", "#274A9F")
_EXAM_DAY_TEXT = ("#0F172A", "#EAF2FF")
_SELECTED_DAY_COLOR = ("#2563EB", "#60A5FA")
_SELECTED_DAY_TEXT = ("#FFFFFF", "#0B1220")
_REGULAR_DAY_TEXT = ("#A8B0BA", "#64748B")


class ScheduleNavigationScreen(ctk.CTkFrame):
    """Review generated exam systems with calendar, details, and export."""

    def __init__(
        self,
        master,
        presenter: ScheduleNavigationPresenter,
        export_presenter: ExportPresenter | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, corner_radius=0, fg_color=_PAGE_BG)
        self.presenter = presenter
        self._export_presenter = export_presenter
        self._on_back = on_back

        self._exam_cells: dict[str, ctk.CTkButton] = {}
        self._selected_iso_date: str | None = None
        self._current_exams_by_iso_date: dict[str, list[ExamRow]] = {}
        self._grid_built = False
        self._metric_labels: dict[str, ctk.CTkLabel] = {}

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
        """Build title, counter, and primary actions."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
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
        if self._export_presenter is not None:
            self._save_button = ctk.CTkButton(
                actions,
                text="Save System",
                width=122,
                fg_color=_PRIMARY,
                hover_color=_PRIMARY_HOVER,
                command=self._handle_save,
            )
            self._save_button.grid(row=0, column=3)

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

        details_card = ctk.CTkFrame(
            main,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        details_card.grid(row=0, column=1, sticky="nsew")
        details_card.grid_columnconfigure(0, weight=1)
        details_card.grid_rowconfigure(2, weight=1)

        self._selected_day_label = ctk.CTkLabel(
            details_card,
            text="Select an exam day",
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

        self._details_body = ctk.CTkScrollableFrame(
            details_card,
            fg_color=_SUBTLE_SURFACE,
            corner_radius=8,
        )
        self._details_body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._details_body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            details_card,
            text="System exams",
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))

        self._schedule_body = ctk.CTkScrollableFrame(
            details_card,
            fg_color="transparent",
            height=170,
        )
        self._schedule_body.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._schedule_body.grid_columnconfigure(0, weight=1)

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
        chosen = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Save Exam Schedule",
            defaultextension=".txt",
            initialfile="exam_schedules.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        result = self._export_presenter.export_current(chosen or None)

        if result.success:
            color = "#147A39"
        elif "cancelled" in result.message.lower():
            color = "#666666"
        else:
            color = "#B00020"
        self._status_label.configure(text=result.message, text_color=color)

    def _refresh(self) -> None:
        """Refresh counter, metrics, calendar highlights, and detail panes."""
        view = self.presenter.current_view()
        if view is None:
            self._counter_label.configure(text="No schedules to display.")
            self._prev_button.configure(state="disabled")
            self._next_button.configure(state="disabled")
            if self._save_button is not None:
                self._save_button.configure(state="disabled")
            return

        if not self._grid_built:
            self._build_relevant_months_grid()
            self._grid_built = True

        self._current_exams_by_iso_date = view.exams_by_iso_date
        if self._selected_iso_date not in self._current_exams_by_iso_date:
            self._selected_iso_date = self._first_exam_date()

        self._counter_label.configure(
            text=f"Reviewing system {view.position} of {view.total}"
        )
        self._refresh_metrics(view)
        self._paint_exam_days(view.exams_by_iso_date)
        self._render_selected_day()
        self._render_system_exam_list(view.sections)

        self._prev_button.configure(
            state="normal" if self.presenter.can_go_previous() else "disabled"
        )
        self._next_button.configure(
            state="normal" if self.presenter.can_go_next() else "disabled"
        )
        if self._save_button is not None:
            self._save_button.configure(state="normal")

    def _refresh_metrics(self, view) -> None:
        """Update summary cards from the current system view."""
        exam_count = sum(len(section.exams) for section in view.sections)
        self._metric_labels["exams"].configure(text=str(exam_count))
        self._metric_labels["days"].configure(text=str(len(view.exams_by_iso_date)))
        self._metric_labels["sections"].configure(text=str(len(view.sections)))
        self._metric_labels["months"].configure(text=str(len(self.presenter.relevant_months())))

    def _build_relevant_months_grid(self) -> None:
        """Draw only months that contain exams in at least one system."""
        for year, month in self.presenter.relevant_months():
            self._build_month(year, month)

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
                command=lambda: None,
                state="disabled",
            )

            exams = exams_by_iso_date.get(iso_date)
            if not exams:
                continue

            selected = iso_date == self._selected_iso_date
            cell.configure(
                text=f"{int(iso_date[-2:])}  ({len(exams)})",
                fg_color=_SELECTED_DAY_COLOR if selected else _EXAM_DAY_COLOR,
                hover=True,
                hover_color=_EXAM_DAY_HOVER,
                text_color=_SELECTED_DAY_TEXT if selected else _EXAM_DAY_TEXT,
                command=lambda d=iso_date: self._select_day(d),
                state="normal",
            )

    def _select_day(self, iso_date: str) -> None:
        """Select a day and refresh the detail panel."""
        self._selected_iso_date = iso_date
        self._paint_exam_days(self._current_exams_by_iso_date)
        self._render_selected_day()

    def _render_selected_day(self) -> None:
        """Show selected-day exam details in the sidebar."""
        for child in self._details_body.winfo_children():
            child.destroy()

        if self._selected_iso_date is None:
            self._selected_day_label.configure(text="Select an exam day")
            self._selected_day_hint.configure(text="Click a highlighted date to inspect its exams.")
            return

        exams = self._current_exams_by_iso_date.get(self._selected_iso_date, [])
        self._selected_day_label.configure(
            text=f"Exams on {self._format_iso_date(self._selected_iso_date)}"
        )
        self._selected_day_hint.configure(
            text=f"{len(exams)} exam{'s' if len(exams) != 1 else ''} scheduled on this date."
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
                    text=f"{exam.exam_date} - {exam.course_number} {exam.course_name}",
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
                f"Instructor: {exam.instructor}\n"
                f"Requirement: {exam.status}\n"
                f"Programs: {exam.program_numbers}"
            ),
            font=("Segoe UI", 11),
            text_color=_MUTED,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

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
