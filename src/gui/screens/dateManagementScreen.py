"""Date management screen for the Version 2.0 GUI workflow."""
from __future__ import annotations

import calendar
import queue
from datetime import date, datetime
from typing import Callable

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.async_runner import AsyncScheduleRunner
from gui.presenters.dateManagementPresenter import DateManagementPresenter
from gui.presenters.schedulingPresenter import GenerationResult, SchedulingPresenter
from scheduling.progressiveGeneration import (
    ProgressiveRankedSnapshot,
    ProgressiveResultState,
)
from gui.screens.themeToggle import (
    THEME_BUTTON_WIDTH,
    ThemeButtonText,
    ThemeToggleCallback,
    current_theme_button_text,
    handle_theme_toggle,
)


_DATE_FORMAT = "%d-%m-%Y"
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
_ACTIVE_DAY_COLOR = ("#DBEAFE", "#1E3A8A")
_ACTIVE_DAY_HOVER = ("#BFDBFE", "#274A9F")
_ACTIVE_DAY_TEXT = ("#0F172A", "#EAF2FF")
_EXCLUDED_DAY_COLOR = ("#FEE2E2", "#5A1F1F")
_EXCLUDED_DAY_HOVER = ("#FECACA", "#7F2A2A")
_EXCLUDED_DAY_TEXT = ("#991B1B", "#FEE2E2")
_OUTSIDE_DAY_TEXT = ("#B8C0CC", "#64748B")


def parse_calendar_date(text: str) -> date:
    """Parse a ``DD-MM-YYYY`` string into a date."""
    return datetime.strptime(text.strip(), _DATE_FORMAT).date()


class DateManagementScreen(ctk.CTkFrame):
    """Calendar screen for editing exam-period windows and excluded dates."""

    def __init__(
        self,
        master,
        presenter: DateManagementPresenter,
        period_presenters: list[DateManagementPresenter] | None = None,
        scheduling_presenter: SchedulingPresenter | None = None,
        runner: AsyncScheduleRunner | None = None,
        on_generation_success: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
        on_theme_toggle: ThemeToggleCallback | None = None,
        theme_button_text: ThemeButtonText = None,
    ) -> None:
        super().__init__(master, corner_radius=0, fg_color=_PAGE_BG)
        self._presenters = period_presenters or [presenter]
        self._current_period_index = 0
        self.presenter = self._presenters[self._current_period_index]
        self._scheduling_presenter = scheduling_presenter
        self._runner = runner or AsyncScheduleRunner()
        self._on_generation_success = on_generation_success
        self._on_back = on_back
        self._on_theme_toggle = on_theme_toggle
        self._theme_button_text = theme_button_text
        self._generation_in_progress = False
        self._progress_queue: queue.Queue = queue.Queue()

        self._period_selector = None
        self._undo_button = None
        self._apply_button = None
        self._back_button = None
        self._generate_button = None
        self._theme_button: ctk.CTkButton | None = None
        self._day_cells: dict[str, ctk.CTkButton] = {}
        self._metric_labels: dict[str, ctk.CTkLabel] = {}

        self._build()
        self._rebuild_calendar()
        self._refresh_status()
        self._refresh_metrics()
        self._refresh_undo_state()

    def _build(self) -> None:
        """Build the modern date-management workspace."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_metrics()
        self._build_controls()
        self._build_calendar_area()
        self._build_footer()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Manage Exam Dates",
            font=("Segoe UI", 24, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Choose an exam period, adjust its window, and mark unavailable days.",
            font=("Segoe UI", 13),
            text_color=_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        if self._on_theme_toggle is not None:
            # Button text tells the user which mode the click will open.
            self._theme_button = ctk.CTkButton(
                header,
                text=current_theme_button_text(self._theme_button_text),
                width=THEME_BUTTON_WIDTH,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                hover_color=("#DCE8FF", "#1E293B"),
                command=self._handle_theme_toggle,
            )
            self._theme_button.grid(row=0, column=1, sticky="ne", rowspan=2)

    def _build_metrics(self) -> None:
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        for column in range(5):
            metrics.grid_columnconfigure(column, weight=1)

        self._build_metric(metrics, 0, "periods", "Periods")
        self._build_metric(metrics, 1, "window", "Window days")
        self._build_metric(metrics, 2, "active", "Active days")
        self._build_metric(metrics, 3, "excluded", "Excluded days")
        self._build_metric(metrics, 4, "hidden", "Hidden exclusions")

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

    def _build_controls(self) -> None:
        controls = ctk.CTkFrame(
            self,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        controls.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 12))
        controls.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            controls,
            text="Exam period",
            font=("Segoe UI", 11, "bold"),
            text_color=_MUTED,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))

        values = self._period_option_labels()
        if len(self._presenters) > 1:
            self._period_selector = ctk.CTkOptionMenu(
                controls,
                values=values,
                command=self._handle_period_selected,
                width=260,
                fg_color=_PRIMARY,
                button_color="#1E40AF",
                button_hover_color=_PRIMARY_HOVER,
            )
            self._period_selector.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))
            self._period_selector.set(values[self._current_period_index])
        else:
            ctk.CTkLabel(
                controls,
                text=values[0],
                font=("Segoe UI", 13, "bold"),
                text_color=_TEXT,
            ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))

        ctk.CTkLabel(
            controls,
            text="Start date",
            font=("Segoe UI", 11, "bold"),
            text_color=_MUTED,
        ).grid(row=0, column=1, sticky="w", padx=(8, 8), pady=(12, 2))
        self._start_entry = ctk.CTkEntry(controls, width=132)
        self._start_entry.grid(row=1, column=1, sticky="w", padx=(8, 8), pady=(0, 14))

        ctk.CTkLabel(
            controls,
            text="End date",
            font=("Segoe UI", 11, "bold"),
            text_color=_MUTED,
        ).grid(row=0, column=2, sticky="w", padx=(8, 8), pady=(12, 2))
        self._end_entry = ctk.CTkEntry(controls, width=132)
        self._end_entry.grid(row=1, column=2, sticky="w", padx=(8, 12), pady=(0, 14))

        self._apply_button = ctk.CTkButton(
            controls,
            text="Apply Period",
            width=118,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_apply_period,
        )
        self._apply_button.grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(0, 14))

        self._undo_button = ctk.CTkButton(
            controls,
            text="Undo",
            width=84,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=(_PRIMARY, "#93C5FD"),
            command=self._handle_undo,
        )
        self._undo_button.grid(row=1, column=4, sticky="w", padx=(0, 12), pady=(0, 14))

        legend = ctk.CTkFrame(controls, fg_color="transparent")
        legend.grid(row=1, column=5, sticky="e", padx=16, pady=(0, 14))
        self._build_legend_item(legend, 0, "Active", _ACTIVE_DAY_COLOR)
        self._build_legend_item(legend, 1, "Excluded", _EXCLUDED_DAY_COLOR)

        self._sync_entries_from_period()

    def _build_legend_item(self, master, column: int, label: str, color) -> None:
        swatch = ctk.CTkLabel(master, text="", width=18, height=18, fg_color=color, corner_radius=5)
        swatch.grid(row=0, column=column * 2, padx=(0 if column == 0 else 12, 6))
        ctk.CTkLabel(master, text=label, text_color=_MUTED, font=("Segoe UI", 11)).grid(
            row=0, column=column * 2 + 1
        )

    def _build_calendar_area(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        card.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Period Calendar",
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 8))

        self._body = ctk.CTkScrollableFrame(
            card,
            fg_color=_SUBTLE_SURFACE,
            border_width=0,
            corner_radius=8,
        )
        self._body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self._body.grid_columnconfigure(0, weight=1)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(footer, text="", text_color=_MUTED)
        self._status_label.grid(row=0, column=0, sticky="w")

        if self._on_back is not None:
            self._back_button = ctk.CTkButton(
                footer,
                text="Back",
                width=90,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                command=self._on_back,
            )
            self._back_button.grid(row=0, column=1, padx=(8, 8))

        self._generate_button = ctk.CTkButton(
            footer,
            text="Generate Exam Schedules",
            width=190,
            height=38,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_generate,
        )
        self._generate_button.grid(row=0, column=2)

    def _rebuild_calendar(self) -> None:
        """Clear and redraw the month cards for the selected period."""
        for child in self._body.winfo_children():
            child.destroy()
        self._day_cells.clear()

        period = self.presenter.current_period()
        for year, month in self._months_between(period.start_date, period.end_date):
            self._build_month(year, month, period.start_date, period.end_date)

        self._paint_days()

    @staticmethod
    def _months_between(start: date, end: date) -> list[tuple[int, int]]:
        months: list[tuple[int, int]] = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append((year, month))
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
        return months

    def _build_month(self, year: int, month: int, start: date, end: date) -> None:
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
            ).grid(row=1, column=col, padx=3, pady=2)

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

                current = date(year, month, day)
                if start <= current <= end:
                    self._build_day_cell(month_frame, 2 + week_index, col, current)
                else:
                    ctk.CTkLabel(
                        month_frame,
                        text=str(day),
                        text_color=_OUTSIDE_DAY_TEXT,
                    ).grid(row=2 + week_index, column=col, padx=3, pady=3)

    def _build_day_cell(
        self,
        parent: ctk.CTkFrame,
        row: int,
        col: int,
        cell_date: date,
    ) -> None:
        iso = cell_date.isoformat()
        cell = ctk.CTkButton(
            parent,
            text=str(cell_date.day),
            height=30,
            corner_radius=7,
            command=lambda d=cell_date: self._handle_day_click(d),
        )
        cell.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
        self._day_cells[iso] = cell

    def _paint_days(self) -> None:
        for iso, cell in self._day_cells.items():
            cell_date = date.fromisoformat(iso)
            if self.presenter.is_excluded(cell_date):
                cell.configure(
                    fg_color=_EXCLUDED_DAY_COLOR,
                    hover_color=_EXCLUDED_DAY_HOVER,
                    text_color=_EXCLUDED_DAY_TEXT,
                    border_width=1,
                    border_color="#DC2626",
                )
            else:
                cell.configure(
                    fg_color=_ACTIVE_DAY_COLOR,
                    hover_color=_ACTIVE_DAY_HOVER,
                    text_color=_ACTIVE_DAY_TEXT,
                    border_width=0,
                )

    def _handle_day_click(self, clicked_date: date) -> None:
        result = self.presenter.on_date_clicked(clicked_date)
        self._paint_days()
        if hasattr(self, "_metric_labels"):
            self._refresh_metrics()
        self._refresh_undo_state()
        self._show_message(result.message, ok=result.success)

    def _handle_theme_toggle(self) -> None:
        """Switch between light and dark mode."""
        handle_theme_toggle(
            self._on_theme_toggle,
            self._theme_button,
            self._theme_button_text,
        )

    def _handle_apply_period(self) -> None:
        try:
            new_start = parse_calendar_date(self._start_entry.get())
            new_end = parse_calendar_date(self._end_entry.get())
        except ValueError:
            self._show_message("Dates must be in DD-MM-YYYY format.", ok=False)
            return

        result = self.presenter.on_edit_period(new_start, new_end)
        if result.success:
            self._rebuild_calendar()
            self._refresh_period_selector()
            if hasattr(self, "_metric_labels"):
                self._refresh_metrics()
            self._refresh_undo_state()
        else:
            self._sync_entries_from_period()
        self._show_message(result.message, ok=result.success)

    def _handle_undo(self) -> None:
        result = self.presenter.undo_last()
        if result.success:
            self._rebuild_calendar()
            self._sync_entries_from_period()
            self._refresh_period_selector()
            if hasattr(self, "_metric_labels"):
                self._refresh_metrics()
            self._refresh_undo_state()
        self._show_message(result.message, ok=result.success)

    def _handle_next(self) -> None:
        """Backward-compatible hook for older wizard tests."""
        on_next = getattr(self, "_on_next", None)
        if on_next is not None:
            on_next()

    def _handle_generate(self) -> None:
        """Generate schedules directly from the final date-review step."""
        if self._scheduling_presenter is None:
            self._show_message("Schedule generator is not available.", ok=False)
            return

        progressive_runner = getattr(self._runner, "run_with_progress", None)
        progressive_generate = getattr(
            self._scheduling_presenter,
            "generate_progressive",
            None,
        )

        if callable(progressive_runner) and callable(progressive_generate):
            accepted = progressive_runner(
                task=lambda token, on_progress: progressive_generate(
                    on_snapshot=on_progress,
                    cancellation_token=token,
                ),
                on_started=self._show_generation_started_progressive,
                on_progress=lambda snapshot: self._progress_queue.put(snapshot),
                on_complete=lambda result: self.after(
                    0,
                    lambda: self._show_generation_result(result),
                ),
                on_error=lambda error: self.after(
                    0,
                    lambda: self._show_generation_error(error),
                ),
            )
        else:
            # Backward-compatible path used by older tests/fakes.
            accepted = self._runner.run(
                task=self._scheduling_presenter.generate,
                on_started=self._show_generation_started,
                on_complete=lambda result: self.after(
                    0,
                    lambda: self._show_generation_result(result),
                ),
                on_error=lambda error: self.after(
                    0,
                    lambda: self._show_generation_error(error),
                ),
            )

        if not accepted:
            self._show_message("Schedule generation is already running.", ok=False)

    def _show_generation_started(self) -> None:
        """Show loading state and lock all editing controls."""
        self._generation_in_progress = True
        self._set_editing_enabled(False)
        self._show_message(
            "Generating schedule systems. This may take a moment.",
            ok=True,
        )

    def _show_generation_started_progressive(self) -> None:
        """Show loading state, lock all editing controls, and start the progress poll.

        Called only from the ``run_with_progress`` code path so the 50 ms
        polling loop is never armed for the backward-compatible ``run()`` path
        (which is synchronous in tests and does not use the progress queue).
        """
        self._show_generation_started()
        # Kick off the 50 ms polling loop that drains the progress queue on the
        # main thread, ensuring no Tkinter widget is ever touched from the
        # background worker thread.
        self.after(50, self._poll_progress_queue)

    def _poll_progress_queue(self) -> None:
        """Drain the progress queue on the main thread, showing only the latest update.

        The background worker posts ``ProgressiveRankedSnapshot`` objects into
        ``self._progress_queue`` via a plain ``put()`` call.  This method runs
        exclusively on the Tkinter main thread (scheduled via ``self.after``) and
        safely consumes those snapshots without any cross-thread widget access.

        Only the most-recent snapshot is rendered so that stale intermediate
        messages do not flash on screen when batches arrive faster than the
        50 ms poll interval.
        """
        progress_queue = getattr(self, "_progress_queue", None)
        latest = None
        if progress_queue is not None:
            try:
                while True:
                    latest = progress_queue.get_nowait()
            except queue.Empty:
                pass

        if latest is not None:
            self._show_generation_progress(latest)

        # Re-schedule only while generation is still running so the loop stops
        # automatically once the completion / error callback lowers the flag.
        if self._generation_in_progress:
            self.after(50, self._poll_progress_queue)



    def _show_generation_progress(
        self,
        snapshot: ProgressiveRankedSnapshot,
    ) -> None:
        """Render a progressive ranking preview status update."""
        if snapshot.state != ProgressiveResultState.PARTIAL:
            return

        self._show_message(snapshot.message, ok=True)

    def _show_generation_result(self, result: GenerationResult) -> None:
        """Handle the scheduler result without leaving the date screen on failure.

        The generation flag is lowered unconditionally *before* any widget
        update so the ``_poll_progress_queue`` loop stops cleanly on both the
        success and the failure path.
        """
        # Always lower the flag first so the polling loop exits cleanly.
        self._generation_in_progress = False

        if result.success and result.schedule_count > 0:
            if 0 < result.displayed_count < result.schedule_count:
                message = (
                    f"{result.schedule_count:,} schedule systems generated. "
                    f"Showing top {result.displayed_count:,} ranked preview."
                )
            else:
                message = (
                    f"{result.schedule_count:,} schedule systems generated successfully."
                )

            self._show_message(message, ok=True)
            if self._on_generation_success is not None:
                self.after(900, self._on_generation_success)
            return

        self._set_editing_enabled(True)
        self._show_message(result.message, ok=False)

    def _show_generation_error(self, error: Exception) -> None:
        """Render unexpected async failures and restore the date controls."""
        self._generation_in_progress = False
        self._set_editing_enabled(True)
        self._show_message(
            f"Schedule generation failed unexpectedly: {type(error).__name__}.",
            ok=False,
        )

    def _set_editing_enabled(self, enabled: bool) -> None:
        """Enable or disable all date editing and navigation controls."""
        state = "normal" if enabled else "disabled"
        for widget in (
            self._period_selector,
            self._start_entry,
            self._end_entry,
            self._apply_button,
            self._back_button,
            self._generate_button,
        ):
            if widget is not None:
                widget.configure(state=state)

        if self._generate_button is not None:
            self._generate_button.configure(
                text="Generate Exam Schedules" if enabled else "Generating..."
            )

        for cell in self._day_cells.values():
            cell.configure(state=state)

        self._refresh_undo_state()

    def _handle_period_selected(self, selected_label: str) -> None:
        labels = self._period_option_labels()
        try:
            self._current_period_index = labels.index(selected_label)
        except ValueError:
            return

        self.presenter = self._presenters[self._current_period_index]
        self._sync_entries_from_period()
        self._rebuild_calendar()
        self._refresh_metrics()
        self._refresh_undo_state()
        self._refresh_status()

    def _sync_entries_from_period(self) -> None:
        period = self.presenter.current_period()
        self._start_entry.delete(0, "end")
        self._start_entry.insert(0, period.start_date.strftime(_DATE_FORMAT))
        self._end_entry.delete(0, "end")
        self._end_entry.insert(0, period.end_date.strftime(_DATE_FORMAT))

    def _refresh_metrics(self) -> None:
        period = self.presenter.current_period()
        window_days = (period.end_date - period.start_date).days + 1
        active_days = len(self.presenter.get_valid_dates())
        excluded_inside_window = self.presenter.count_excluded_inside_window()
        excluded_outside_window = self.presenter.count_excluded_outside_window()

        self._metric_labels["periods"].configure(
            text=f"{self._current_period_index + 1}/{len(self._presenters)}"
        )
        self._metric_labels["window"].configure(text=str(window_days))
        self._metric_labels["active"].configure(text=str(active_days))
        self._metric_labels["excluded"].configure(text=str(excluded_inside_window))
        self._metric_labels["hidden"].configure(text=str(excluded_outside_window))

    def _refresh_status(self) -> None:
        self._status_label.configure(
            text=self._message_with_hidden_exclusions(
                "Click a calendar day to exclude it or re-enable it."
            ),
            text_color=_MUTED,
        )

    def _show_message(self, text: str, ok: bool) -> None:
        text = self._message_with_hidden_exclusions(text)
        self._status_label.configure(
            text=text,
            text_color="#147A39" if ok else "#B00020",
        )

    def _period_option_labels(self) -> list[str]:
        labels: list[str] = []
        for index, presenter in enumerate(self._presenters, start=1):
            period = presenter.current_period()
            semester = getattr(period, "semester", "FALL")
            moed = getattr(period, "moed", "Aleph")
            labels.append(
                (
                    f"{index}. {semester} {moed} | "
                    f"{period.start_date.strftime(_DATE_FORMAT)} - "
                    f"{period.end_date.strftime(_DATE_FORMAT)}"
                )
            )
        return labels

    def _refresh_undo_state(self) -> None:
        if getattr(self, "_undo_button", None) is None:
            return

        can_undo = self.presenter.can_undo()
        if self._generation_in_progress:
            can_undo = False
        self._undo_button.configure(
            state="normal" if can_undo else "disabled",
            text_color=(_PRIMARY, "#93C5FD") if can_undo else _MUTED,
        )

    def _message_with_hidden_exclusions(self, text: str) -> str:
        hidden_count = self.presenter.count_excluded_outside_window()
        if hidden_count == 0:
            return text
        suffix = (
            f" {hidden_count} excluded date"
            f"{'s are' if hidden_count != 1 else ' is'} outside this window."
        )
        return f"{text}{suffix}"

    def _refresh_period_selector(self) -> None:
        if getattr(self, "_period_selector", None) is None:
            return

        labels = self._period_option_labels()
        self._period_selector.configure(values=labels)
        self._period_selector.set(labels[self._current_period_index])
