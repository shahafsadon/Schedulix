"""Output screen: navigate and visualize generated schedules (SCRUM-126).

Passive MVP View. It renders the current exam system on a calendar, showing only
the months that actually contain exams (computed across all systems so the month
list stays stable during navigation). Exam days are highlighted and clickable;
clicking one opens a popup with that day's exam details. Previous/Next move
between systems and a "System X of Y" counter sits at the top.

Performance notes:
- Only relevant months are drawn (a period spans a few months, not the whole
  year), which keeps the scrollable area small and smooth.
- Regular days are lightweight CTkLabels; only exam days are CTkButtons. This
  minimizes the number of heavy widgets in the scroll region.
- The grid is built once; navigation only repaints the exam-day cells, so
  Next/Previous stay instant.

Navigation logic and view-model building belong to the presenter; this screen
neither generates nor filters anything. Export (Save) is SCRUM-127's scope.
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
# Colors are (light_mode, dark_mode) pairs as expected by customtkinter.
_EXAM_DAY_COLOR = ("#ffd6d6", "#5a2b2b")
_EXAM_DAY_HOVER = ("#ffbcbc", "#6e3636")
_EXAM_DAY_TEXT = ("#7a0000", "#ffe0e0")
_REGULAR_DAY_TEXT = ("#333333", "#cfcfcf")


class ScheduleNavigationScreen(ctk.CTkFrame):
    """Shows one generated exam system on a (relevant-months) calendar."""

    def __init__(
        self,
        master,
        presenter: ScheduleNavigationPresenter,
        export_presenter: ExportPresenter | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        """Create the navigation screen.

        Args:
            master: the parent customTkinter container.
            presenter: owns the current-system index and builds the view model.
            export_presenter: drives the Save action; when None, the Save button
                is hidden (useful for standalone preview without the wizard).
            on_back: optional callback to return to the previous wizard step.
        """
        super().__init__(master, corner_radius=0)
        self.presenter = presenter
        self._export_presenter = export_presenter
        self._on_back = on_back

        # Exam-day cells only, keyed by ISO date "YYYY-MM-DD". Regular days are
        # plain labels we never need to touch again, so they are not stored.
        self._exam_cells: dict[str, ctk.CTkButton] = {}
        # Whether the static month grid has been built yet (built once).
        self._grid_built = False

        self._build()
        self._refresh()

    def _build(self) -> None:
        """Build the static layout: title, counter, scrollable body, nav bar."""
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Generated Exam Schedules",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        self._counter_label = ctk.CTkLabel(self, text="", text_color="#666666")
        self._counter_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        # Scrollable area holding the relevant months only.
        self._body = ctk.CTkScrollableFrame(self)
        self._body.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        self._body.grid_columnconfigure(0, weight=1)

        self._build_nav_bar()

    def _build_nav_bar(self) -> None:
        """Build the bottom navigation bar (Back / Previous / Next)."""
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        nav.grid_columnconfigure(0, weight=1)

        if self._on_back is not None:
            ctk.CTkButton(
                nav,
                text="Back",
                width=90,
                fg_color="transparent",
                border_width=1,
                command=self._on_back,
            ).grid(row=0, column=1, padx=(8, 8))

        self._prev_button = ctk.CTkButton(
            nav, text="< Previous", width=110, command=self._handle_previous
        )
        self._prev_button.grid(row=0, column=2, padx=(8, 8))

        self._next_button = ctk.CTkButton(
            nav, text="Next >", width=110, command=self._handle_next
        )
        self._next_button.grid(row=0, column=3)

        # Save button is only shown when an export presenter was injected, so
        # the screen stays usable as a pure preview without the export wiring.
        self._save_button = None
        if self._export_presenter is not None:
            self._save_button = ctk.CTkButton(
                nav, text="Save System", width=120, command=self._handle_save
            )
            self._save_button.grid(row=0, column=4, padx=(8, 0))

        # Status line under the nav row: shows the last export message.
        self._status_label = ctk.CTkLabel(nav, text="", text_color="#666666")
        self._status_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

    def _handle_next(self) -> None:
        """Advance to the next system and repaint the exam days."""
        self.presenter.next()
        self._refresh()

    def _handle_save(self) -> None:
        """Ask the user for a destination file then export the current system.

        Opening the Save-As dialog is a customtkinter/tkinter concern, so it
        belongs in the View. The chosen path (or None on cancel) is forwarded
        to the presenter, which performs the actual export and returns a
        display-ready result.
        """
        # asksaveasfilename returns "" when the user cancels; normalize to None
        # so the presenter has a single "cancelled" signal to react to.
        chosen = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Save Exam Schedule",
            defaultextension=".txt",
            initialfile="exam_schedules.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        result = self._export_presenter.export_current(chosen or None)

        # Surface the outcome to the user. Color hint: green for success,
        # grey for cancel, red for failure.
        if result.success:
            color = "#2e7d32"   # green
        elif "cancelled" in result.message.lower():
            color = "#666666"   # grey (cancellation is not an error)
        else:
            color = "#B00020"   # red
        self._status_label.configure(text=result.message, text_color=color)

    def _handle_previous(self) -> None:
        """Go to the previous system and repaint the exam days."""
        self.presenter.previous()
        self._refresh()

    def _refresh(self) -> None:
        """Update counter, repaint exam days, and refresh nav-button states."""
        view = self.presenter.current_view()
        if view is None:
            self._counter_label.configure(text="No schedules to display.")
            self._prev_button.configure(state="disabled")
            self._next_button.configure(state="disabled")
            if self._save_button is not None:
                self._save_button.configure(state="disabled")
            return

        # Build the (relevant-months) grid once. The month list is computed
        # across all systems, so it never needs rebuilding during navigation.
        if not self._grid_built:
            self._build_relevant_months_grid()
            self._grid_built = True

        self._counter_label.configure(
            text=f"System {view.position} of {view.total}"
        )
        self._paint_exam_days(view.exams_by_iso_date)

        self._prev_button.configure(
            state="normal" if self.presenter.can_go_previous() else "disabled"
        )
        self._next_button.configure(
            state="normal" if self.presenter.can_go_next() else "disabled"
        )
        if self._save_button is not None:
            # Save is always available when at least one schedule exists.
            self._save_button.configure(state="normal")

    def _build_relevant_months_grid(self) -> None:
        """Draw only the months that contain an exam in any system."""
        for (year, month) in self.presenter.relevant_months():
            self._build_month(year, month)

    def _build_month(self, year: int, month: int) -> None:
        """Create one month's header + weekday row + grid of day cells.

        Regular days are lightweight labels; exam days are buttons (stored in
        self._exam_cells) so navigation can recolor and rewire them cheaply.
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
        """Create one day.

        We do not yet know which system is active when building the grid, so we
        cannot tell exam days from regular days here. Every cell starts as a
        lightweight label; _paint_exam_days later promotes the exam days of the
        current system to highlighted buttons and demotes the others back.
        Because promotion/demotion needs a single widget type to swap styling
        on, we use a button for every day but keep regular days visually flat
        and disabled (so they read as plain text, not as clickable buttons).
        """
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        cell = ctk.CTkButton(
            parent,
            text=str(day),
            width=32,
            height=28,
            fg_color="transparent",
            hover=False,
            text_color=_REGULAR_DAY_TEXT,
            command=lambda: None,
            state="disabled",
        )
        cell.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
        self._exam_cells[iso] = cell

    def _paint_exam_days(
        self,
        exams_by_iso_date: dict[str, list[ExamRow]],
    ) -> None:
        """Repaint cells so only the current system's exam days are highlighted.

        First every cell is reset to the flat regular-day look, then each exam
        day of the current system is promoted to a highlighted, clickable
        button. This is O(number of cells) but touches only color/command, which
        is far cheaper than rebuilding widgets.
        """
        # Reset all cells to the flat, non-interactive regular-day look.
        for cell in self._exam_cells.values():
            cell.configure(
                fg_color="transparent",
                hover=False,
                text_color=_REGULAR_DAY_TEXT,
                command=lambda: None,
                state="disabled",
            )

        # Promote the current system's exam days.
        for iso_date, exams in exams_by_iso_date.items():
            cell = self._exam_cells.get(iso_date)
            if cell is None:
                # Defensive: an exam day outside the drawn months.
                continue
            cell.configure(
                fg_color=_EXAM_DAY_COLOR,
                hover=True,
                hover_color=_EXAM_DAY_HOVER,
                text_color=_EXAM_DAY_TEXT,
                # Default args bind the current iteration's values, not the last.
                command=lambda d=iso_date, e=exams: self._show_day_popup(d, e),
                state="normal",
            )

    def _show_day_popup(self, iso_date: str, exams: list[ExamRow]) -> None:
        """Open a modal popup listing all exams scheduled on `iso_date`."""
        popup = ctk.CTkToplevel(self)
        popup.title(f"Exams on {iso_date}")
        popup.geometry("520x340")
        popup.transient(self.winfo_toplevel())
        popup.grab_set()

        ctk.CTkLabel(
            popup,
            text=f"Exams scheduled on {iso_date}",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(12, 6))

        body = ctk.CTkScrollableFrame(popup)
        body.pack(fill="both", expand=True, padx=12, pady=4)

        for exam in exams:
            row = ctk.CTkFrame(body)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row,
                text=f"{exam.course_number}  -  {exam.course_name}",
                font=("Segoe UI", 12, "bold"),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(6, 0))
            ctk.CTkLabel(
                row,
                text=(
                    f"Instructor: {exam.instructor}    "
                    f"Requirement: {exam.status}    "
                    f"Programs: {exam.program_numbers}"
                ),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkButton(popup, text="Close", width=90, command=popup.destroy).pack(
            pady=(4, 12)
        )