"""Date management screen for the Version 2.0 GUI (SCRUM-124).

This is wizard step C from section 4.2 of the design document: the user sees a
calendar for the active exam period, clicks a day to toggle it between "active"
and "excluded" (the cell changes color), and can adjust the period's scheduling
window (start/end dates) in the same screen.

As a passive MVP View it owns no domain logic. Every user action is delegated to
the injected ``DateManagementPresenter``:
- clicking a day  -> presenter.on_date_clicked(date)         (Command: toggle)
- editing a window -> presenter.on_edit_period(start, end)   (Command: edit)
- undo            -> presenter.undo_last()                   (one-step revert)
The presenter returns a ``CommandResult`` carrying the refreshed valid-date
list, which the View uses to repaint the calendar. The View never imports or
touches the Command classes, the cache, or the scheduling engine directly.

Calendar rendering mirrors the SCRUM-126 output screen: a month grid built with
``calendar.monthcalendar``, lightweight day buttons, and (light, dark) color
pairs as expected by customtkinter. Only the months spanned by the active
period are drawn, and the grid is rebuilt whenever the window changes (an edit
can grow or shrink the set of months).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Callable

# The GUI layer depends on customtkinter. We fail early with a clear, actionable
# message rather than a bare ImportError, since this is the most common setup
# mistake (running without installing the project requirements).
try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from gui.dateManagementPresenter import DateManagementPresenter


# Date format shown in the edit fields and parsed back from them. Matches the
# DD-MM-YYYY convention used throughout the input files (see ExamPeriodsReader).
_DATE_FORMAT = "%d-%m-%Y"

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_WEEKDAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Colors are (light_mode, dark_mode) pairs as expected by customtkinter.
# Excluded days are red (blocked); active in-window days are a neutral fill.
_EXCLUDED_DAY_COLOR = ("#ffd6d6", "#5a2b2b")
_EXCLUDED_DAY_HOVER = ("#ffbcbc", "#6e3636")
_EXCLUDED_DAY_TEXT = ("#7a0000", "#ffe0e0")
_ACTIVE_DAY_COLOR = ("#e6f0e6", "#2b3b2b")
_ACTIVE_DAY_HOVER = ("#d2e6d2", "#365036")
_ACTIVE_DAY_TEXT = ("#1f5130", "#d6f0d6")


def parse_calendar_date(text: str) -> date:
    """Parse a ``DD-MM-YYYY`` string into a ``date``.

    Kept as a module-level function (not a method) so the parsing rule can be
    unit-tested without constructing a customtkinter widget. Raises ``ValueError``
    on a malformed string, which the View catches to show an error message.

    Args:
        text: the date string typed by the user, e.g. "29-01-2026".

    Returns:
        The parsed ``date`` object.

    Raises:
        ValueError: if ``text`` does not match the expected DD-MM-YYYY format.
    """
    return datetime.strptime(text.strip(), _DATE_FORMAT).date()


class DateManagementScreen(ctk.CTkFrame):
    """Calendar screen to exclude/activate days and edit the period window."""

    def __init__(
        self,
        master,
        presenter: DateManagementPresenter,
        on_next: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        """Create the date management screen.

        Args:
            master: the parent customTkinter container.
            presenter: drives date toggling, period editing, and undo.
            on_next: optional callback fired when the user moves to the next step.
            on_back: optional callback fired when the user goes back a step.
        """
        super().__init__(master, corner_radius=0)
        self.presenter = presenter
        # Navigation callbacks are optional so the screen can be shown/tested
        # standalone; the wizard shell wires them in the full application.
        self._on_next = on_next
        self._on_back = on_back

        # Day cells keyed by ISO date "YYYY-MM-DD". Only in-window days are
        # stored, since those are the only cells the user can toggle and the
        # only ones we repaint after a change.
        self._day_cells: dict[str, ctk.CTkButton] = {}

        self._build()
        # Draw the calendar for the period's current window and color the days.
        self._rebuild_calendar()
        self._refresh_status()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Build the static layout: title, edit panel, scrollable calendar, footer."""
        # The calendar body (row 2) takes all spare vertical space.
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Manage Exam Dates",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        self._build_edit_panel()

        # Scrollable area holding the month grid(s) of the active window.
        self._body = ctk.CTkScrollableFrame(self)
        self._body.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        self._body.grid_columnconfigure(0, weight=1)

        self._build_footer()

    def _build_edit_panel(self) -> None:
        """Build the in-screen period-editing panel (start/end fields + Apply).

        Implements the "Edit semester periods" sub-task: the user types a new
        start and end date and clicks Apply; the View delegates to
        ``presenter.on_edit_period`` and redraws the calendar on success.
        """
        panel = ctk.CTkFrame(self, fg_color="transparent")
        panel.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        ctk.CTkLabel(panel, text="Period start (DD-MM-YYYY):").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self._start_entry = ctk.CTkEntry(panel, width=120)
        self._start_entry.grid(row=0, column=1, padx=(0, 16))

        ctk.CTkLabel(panel, text="Period end (DD-MM-YYYY):").grid(
            row=0, column=2, sticky="w", padx=(0, 6)
        )
        self._end_entry = ctk.CTkEntry(panel, width=120)
        self._end_entry.grid(row=0, column=3, padx=(0, 16))

        ctk.CTkButton(
            panel, text="Apply Period", width=110, command=self._handle_apply_period
        ).grid(row=0, column=4, padx=(0, 8))

        ctk.CTkButton(
            panel,
            text="Undo",
            width=80,
            fg_color="transparent",
            border_width=1,
            command=self._handle_undo,
        ).grid(row=0, column=5)

        # Prefill the entries with the period's current window so the user edits
        # the real values rather than typing from scratch.
        self._sync_entries_from_period()

    def _build_footer(self) -> None:
        """Build the footer: status label and Back/Next navigation buttons."""
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        # Column 0 stretches so the status label sits left and buttons sit right.
        footer.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(footer, text="", text_color="#666666")
        self._status_label.grid(row=0, column=0, sticky="w")

        # Back is only shown when a callback exists (i.e. inside the wizard).
        if self._on_back is not None:
            ctk.CTkButton(
                footer,
                text="Back",
                width=90,
                fg_color="transparent",
                border_width=1,
                command=self._on_back,
            ).grid(row=0, column=1, padx=(8, 8))

        # Next is always present; date management is optional, so the user may
        # proceed without excluding anything.
        ctk.CTkButton(
            footer, text="Next", width=90, command=self._handle_next
        ).grid(row=0, column=2)

    # ------------------------------------------------------------------
    # Calendar rendering
    # ------------------------------------------------------------------

    def _rebuild_calendar(self) -> None:
        """Clear and redraw the month grid for the period's current window.

        Called on first build and again after a successful period edit, because
        changing start/end can add or remove whole months from the view.
        """
        # Drop any previously drawn months and their cached cells.
        for child in self._body.winfo_children():
            child.destroy()
        self._day_cells.clear()

        # Draw every month spanned by the active window. The presenter exposes
        # the valid dates, but we draw full months (start..end) so the user sees
        # the days they can toggle in their normal calendar context.
        start = self.presenter._exam_period.start_date
        end = self.presenter._exam_period.end_date
        for (year, month) in self._months_between(start, end):
            self._build_month(year, month, start, end)

        # Color the days according to the current excluded/active state.
        self._paint_days()

    @staticmethod
    def _months_between(start: date, end: date) -> list[tuple[int, int]]:
        """Return the (year, month) pairs spanned by the window, in order."""
        months: list[tuple[int, int]] = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append((year, month))
            # Advance one calendar month, rolling over to January of next year.
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
        return months

    def _build_month(self, year: int, month: int, start: date, end: date) -> None:
        """Create one month's header + weekday row + grid of day cells.

        Only days inside the [start, end] window become interactive cells (they
        can be toggled); days outside the window are flat, disabled labels so the
        calendar reads naturally without inviting clicks that do nothing.
        """
        month_frame = ctk.CTkFrame(self._body)
        month_frame.pack(fill="x", pady=(8, 4))
        for col in range(7):
            month_frame.grid_columnconfigure(col, weight=1, uniform="day")

        ctk.CTkLabel(
            month_frame,
            text=f"{_MONTH_NAMES[month - 1]} {year}",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, columnspan=7, sticky="w", padx=8, pady=(6, 2))

        for col, label in enumerate(_WEEKDAY_HEADERS):
            ctk.CTkLabel(
                month_frame,
                text=label,
                font=("Segoe UI", 10, "bold"),
                text_color="#888888",
            ).grid(row=1, column=col, padx=1, pady=1)

        for week_index, week in enumerate(calendar.monthcalendar(year, month)):
            for col, day in enumerate(week):
                if day == 0:
                    # Padding cell for days outside this month.
                    ctk.CTkLabel(month_frame, text="").grid(
                        row=2 + week_index, column=col, padx=1, pady=1
                    )
                    continue

                current = date(year, month, day)
                if start <= current <= end:
                    # In-window: an interactive cell the user can toggle.
                    self._build_day_cell(month_frame, 2 + week_index, col, current)
                else:
                    # Out-of-window: a flat, non-interactive label.
                    ctk.CTkLabel(
                        month_frame,
                        text=str(day),
                        text_color="#bbbbbb",
                    ).grid(row=2 + week_index, column=col, padx=1, pady=1)

    def _build_day_cell(
        self,
        parent: ctk.CTkFrame,
        row: int,
        col: int,
        cell_date: date,
    ) -> None:
        """Create one interactive in-window day cell and register it by ISO date.

        The cell's color is set later by ``_paint_days``; here we only wire the
        click to the presenter via the day's date.
        """
        iso = cell_date.isoformat()
        cell = ctk.CTkButton(
            parent,
            text=str(cell_date.day),
            width=32,
            height=28,
            # Default arg binds this iteration's date, not the loop's last value.
            command=lambda d=cell_date: self._handle_day_click(d),
        )
        cell.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
        self._day_cells[iso] = cell

    def _paint_days(self) -> None:
        """Color every in-window cell as excluded (red) or active (neutral).

        The presenter is the single source of truth for the excluded state, so
        each cell is colored by asking ``presenter.is_excluded`` for its date.
        """
        for iso, cell in self._day_cells.items():
            cell_date = date.fromisoformat(iso)
            if self.presenter.is_excluded(cell_date):
                cell.configure(
                    fg_color=_EXCLUDED_DAY_COLOR,
                    hover_color=_EXCLUDED_DAY_HOVER,
                    text_color=_EXCLUDED_DAY_TEXT,
                )
            else:
                cell.configure(
                    fg_color=_ACTIVE_DAY_COLOR,
                    hover_color=_ACTIVE_DAY_HOVER,
                    text_color=_ACTIVE_DAY_TEXT,
                )

    # ------------------------------------------------------------------
    # Event handlers (delegate to the presenter)
    # ------------------------------------------------------------------

    def _handle_day_click(self, clicked_date: date) -> None:
        """Toggle a day's excluded/active state via the presenter, then repaint."""
        result = self.presenter.on_date_clicked(clicked_date)
        # Recolor every cell from the presenter's updated state and echo the
        # command's message (green for success, red otherwise).
        self._paint_days()
        self._show_message(result.message, ok=result.success)

    def _handle_apply_period(self) -> None:
        """Apply a new start/end window from the edit fields via the presenter.

        Parses the two date fields, delegates to ``on_edit_period``, and on
        success rebuilds the calendar (the month set may have changed). A parse
        error or a presenter rejection is shown in red and leaves the calendar
        untouched.
        """
        # Parse the fields first; a malformed date never reaches the presenter.
        try:
            new_start = parse_calendar_date(self._start_entry.get())
            new_end = parse_calendar_date(self._end_entry.get())
        except ValueError:
            self._show_message(
                "Dates must be in DD-MM-YYYY format.", ok=False
            )
            return

        result = self.presenter.on_edit_period(new_start, new_end)
        if result.success:
            # The window changed: redraw months and recolor days.
            self._rebuild_calendar()
        else:
            # Rejected (e.g. inverted range): snap the fields back to the real
            # window so the displayed values stay consistent with the period.
            self._sync_entries_from_period()
        self._show_message(result.message, ok=result.success)

    def _handle_undo(self) -> None:
        """Revert the last toggle or period edit via the presenter, then refresh."""
        result = self.presenter.undo_last()
        if result.success:
            # An undone edit can change the window, so rebuild to be safe; this
            # also recolors days for an undone toggle.
            self._rebuild_calendar()
            self._sync_entries_from_period()
        self._show_message(result.message, ok=result.success)

    def _handle_next(self) -> None:
        """Move to the next wizard step if a navigation callback was provided."""
        if self._on_next is not None:
            self._on_next()

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _sync_entries_from_period(self) -> None:
        """Fill the start/end entry fields with the period's current window."""
        period = self.presenter._exam_period
        self._start_entry.delete(0, "end")
        self._start_entry.insert(0, period.start_date.strftime(_DATE_FORMAT))
        self._end_entry.delete(0, "end")
        self._end_entry.insert(0, period.end_date.strftime(_DATE_FORMAT))

    def _refresh_status(self) -> None:
        """Show a neutral hint describing how to use the screen."""
        self._status_label.configure(
            text="Click a day to exclude or re-activate it.",
            text_color="#666666",
        )

    def _show_message(self, text: str, ok: bool) -> None:
        """Display a status message, green on success and red on failure."""
        self._status_label.configure(
            text=text,
            text_color="#1f7a1f" if ok else "#B00020",
        )