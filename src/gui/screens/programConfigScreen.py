"""Unified program configuration screen for the Version 2.0 GUI (SCRUM-122 + 123).

This single screen implements section 4.2 of the design document: a list of all
available study programs where each row can be (a) selected for scheduling via a
checkbox, up to the five-program maximum, and (b) expanded in place via a ">"
toggle to reveal that program's courses grouped by year and semester.

As a passive MVP view it owns no data logic. It orchestrates two presenters:
- ProgramSelectionPresenter drives the checkboxes and the 5-max rule.
- ProgramDetailsPresenter supplies the grouped course details shown when a row
  is expanded.
"""
from __future__ import annotations

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

from gui.presenters.programSelectionPresenter import ProgramSelectionPresenter
from gui.presenters.programDetailsPresenter import ProgramDetailsPresenter, ProgramDetails


_PAGE_BG = ("#F3F6FB", "#0B1220")
_SURFACE = ("#FFFFFF", "#151B26")
_SUBTLE_SURFACE = ("#F8FAFC", "#101826")
_BORDER = ("#D8E2F0", "#2D3748")
_TEXT = ("#111827", "#F8FAFC")
_MUTED = ("#5F6368", "#A8A8A8")
_PRIMARY = "#2563EB"
_PRIMARY_HOVER = "#1D4ED8"


class ProgramConfigScreen(ctk.CTkFrame):
    """List of programs with per-row selection checkbox and expandable details."""

    def __init__(
        self,
        master,
        selection_presenter: ProgramSelectionPresenter,
        details_presenter: ProgramDetailsPresenter,
        on_next: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        """Create the program configuration screen.

        Args:
            master: the parent customTkinter container.
            selection_presenter: drives the checkboxes and the five-program limit.
            details_presenter: supplies the per-program course details.
            on_next: optional callback fired when the user confirms the selection.
            on_back: optional callback fired when the user goes back a step.
        """
        super().__init__(master, corner_radius=0, fg_color=_PAGE_BG)
        # Two presenters, two responsibilities: selecting vs inspecting.
        self.selection_presenter = selection_presenter
        self.details_presenter = details_presenter
        # Navigation callbacks are optional so the screen can be shown/tested
        # standalone; the wizard shell wires them in the full application.
        self._on_next = on_next
        self._on_back = on_back

        # Per-program widget registries, keyed by program number, so each row
        # can be updated independently (revert a checkbox, expand one row, ...).
        self._checkbox_vars: dict[str, ctk.BooleanVar] = {}      # checkbox state
        self._expanded: dict[str, bool] = {}                     # is row open?
        self._detail_frames: dict[str, ctk.CTkFrame] = {}        # details container
        self._toggle_buttons: dict[str, ctk.CTkButton] = {}      # the ">"/"v" button

        # Build the widget tree, then sync the footer with the initial state.
        self._build()
        self._refresh_status()

    def _build(self) -> None:
        """Build the screen layout: title, scrollable program list, footer."""
        # Row 1 (the list) takes all spare vertical space; title/footer stay fixed.
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Select Study Programs",
            font=("Segoe UI", 24, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=f"Choose up to {self.selection_presenter.max_programs} programs and inspect their courses before scheduling.",
            font=("Segoe UI", 13),
            text_color=_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self._selection_badge = ctk.CTkLabel(
            header,
            text=f"0 / {self.selection_presenter.max_programs} selected",
            font=("Segoe UI", 12, "bold"),
            fg_color=("#E8F1FF", "#111D33"),
            text_color=(_PRIMARY, "#93C5FD"),
            corner_radius=14,
            padx=12,
            pady=5,
        )
        self._selection_badge.grid(row=0, column=1, sticky="ne", rowspan=2)

        # Every program row lives in one scrollable column so expanding a row
        # pushes the rows below it downward, as described in section 4.2.
        self._list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        self._list_frame.grid_columnconfigure(0, weight=1)

        programs = self.selection_presenter.available_programs
        if not programs:
            # No data loaded yet: guide the user instead of showing a blank list.
            ctk.CTkLabel(
                self._list_frame,
                text="No programs found. Load a courses file first.",
                text_color=_MUTED,
            ).grid(row=0, column=0, sticky="w", padx=16, pady=16)
        else:
            # One self-contained row widget per selectable program.
            for program in programs:
                self._build_program_row(program)

        self._build_footer()

    def _build_program_row(self, program_number: str) -> None:
        """Build one program row: a selection checkbox plus an expand toggle.

        The details frame is created here but stays empty and hidden until the
        user expands the row for the first time.
        """
        # A row container holds the header line (row 0) plus a details frame
        # (row 1) that is only gridded in when the row is expanded.
        row = ctk.CTkFrame(
            self._list_frame,
            fg_color=_SUBTLE_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        row.pack(fill="x", padx=10, pady=(10, 0))
        # Column 1 stretches so the toggle button is pushed to the far right.
        row.grid_columnconfigure(1, weight=1)

        # (a) Selection checkbox: toggles whether the program goes to scheduling.
        # The BooleanVar mirrors the visual state and lets us revert a rejected
        # click (see _on_check) without rebuilding the widget.
        variable = ctk.BooleanVar(
            value=self.selection_presenter.is_selected(program_number)
        )
        checkbox = ctk.CTkCheckBox(
            row,
            text=f"Program {program_number}",
            variable=variable,
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            # default argument binds the current program to this row's callback,
            # avoiding the classic late-binding closure bug inside the loop.
            command=lambda current=program_number: self._on_check(current),
        )
        checkbox.grid(row=0, column=0, columnspan=2, sticky="w", padx=(14, 8), pady=12)
        self._checkbox_vars[program_number] = variable

        # (b) Expand/collapse toggle: reveals the program's course details.
        toggle = ctk.CTkButton(
            row,
            text=">",
            width=36,
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=(_PRIMARY, "#93C5FD"),
            command=lambda current=program_number: self._on_toggle(current),
        )
        toggle.grid(row=0, column=2, sticky="e", padx=(8, 14), pady=10)
        self._toggle_buttons[program_number] = toggle

        # Details frame is created now but NOT gridded yet: it stays empty and
        # hidden until the row is first expanded (lazy build in _on_toggle).
        details_frame = ctk.CTkFrame(
            row,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        details_frame.grid_columnconfigure(0, weight=1)
        self._detail_frames[program_number] = details_frame
        self._expanded[program_number] = False

    def _build_footer(self) -> None:
        """Build the footer: selection counter and Back/Next navigation buttons."""
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        # Column 0 stretches so the status label sits left and buttons sit right.
        footer.grid_columnconfigure(0, weight=1)

        # Live counter ("Selected: X / 5") and rejection messages share this label.
        self._status_label = ctk.CTkLabel(footer, text="", text_color=_MUTED)
        self._status_label.grid(row=0, column=0, sticky="w")

        # Back is only shown when a callback exists (i.e. inside the wizard).
        if self._on_back is not None:
            ctk.CTkButton(
                footer,
                text="Back",
                width=90,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                command=self._on_back,
            ).grid(row=0, column=1, padx=(8, 8))

        # Kept as an attribute because _refresh_status enables/disables it.
        self._next_button = ctk.CTkButton(
            footer,
            text="Next",
            width=100,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_next,
        )
        self._next_button.grid(row=0, column=2)

    def _on_check(self, program_number: str) -> None:
        """Handle a checkbox click by delegating the toggle to the presenter.

        If the presenter rejects the change (e.g. the five-program limit is
        reached), the checkbox is reverted to the presenter's real state and a
        short message is shown.
        """
        # All selection logic lives in the presenter; the view only reacts.
        result = self.selection_presenter.toggle(program_number)
        if not result.accepted:
            # Rejected: snap the checkbox back to the presenter's real state
            # (the click is visually undone) and surface the reason in red.
            self._checkbox_vars[program_number].set(
                self.selection_presenter.is_selected(program_number)
            )
            self._status_label.configure(text=result.message, text_color="#B00020")
            return
        # Accepted: refresh the counter and the Next button's enabled state.
        self._refresh_status()

    def _on_toggle(self, program_number: str) -> None:
        """Expand or collapse a program row in place.

        Details are built lazily the first time a row is opened, then shown or
        hidden on later toggles. The toggle caption switches between ">" and "v".
        """
        # Flip the stored open/closed flag for this row.
        expanded = not self._expanded[program_number]
        self._expanded[program_number] = expanded
        frame = self._detail_frames[program_number]

        if expanded:
            # Build the details only once: if the frame has no children yet,
            # this is the first expansion, so populate it now (lazy build).
            if not frame.winfo_children():
                self._fill_details(
                    frame, self.details_presenter.get_details(program_number)
                )
            # Grid the frame on row 1 of the row container, spanning all columns
            # so it sits directly under the checkbox + toggle and pushes the
            # following rows down.
            frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 12))
            self._toggle_buttons[program_number].configure(text="v")
        else:
            # Collapse: detach the frame from the grid (it keeps its children,
            # so re-expanding is instant and needs no rebuild).
            frame.grid_forget()
            self._toggle_buttons[program_number].configure(text=">")

    def _fill_details(self, frame: ctk.CTkFrame, details: ProgramDetails) -> None:
        """Render a program's courses inside its details frame.

        Courses are shown grouped by year and semester; each course line lists
        its number, name, requirement type and evaluation method.
        """
        if details.course_count == 0:
            # Defensive: a selected program with no courses still gets a clear
            # placeholder rather than an empty, confusing panel.
            ctk.CTkLabel(
                frame,
                text="No courses found for this program.",
                text_color=_MUTED,
            ).grid(row=0, column=0, sticky="w", padx=12, pady=10)
            return

        # grid_row advances manually because headers and course lines are mixed
        # in a single column; the presenter already returns groups pre-sorted.
        grid_row = 0
        for group in details.groups:
            # Sub-header marking each (year, semester) slot.
            ctk.CTkLabel(
                frame,
                text=f"Year {group.year} - {group.semester}",
                font=("Segoe UI", 12, "bold"),
                text_color=_TEXT,
            ).grid(row=grid_row, column=0, sticky="w", padx=12, pady=(10, 4))
            grid_row += 1

            # One readable line per course under its slot header.
            for course in group.courses:
                line = (
                    f"{course.course_number}  |  {course.name}  |  "
                    f"{course.status}  |  {course.evaluation_type}"
                )
                ctk.CTkLabel(frame, text=line, anchor="w").grid(
                    row=grid_row,
                    column=0,
                    sticky="w",
                    padx=24,
                    pady=2,
                )
                grid_row += 1

    def _handle_next(self) -> None:
        """Move to the next wizard step, but only if the selection is valid.

        When nothing is selected the presenter blocks the move and the user is
        asked to pick at least one program.
        """
        # The presenter is the single source of truth for "is the selection OK".
        if not self.selection_presenter.can_proceed():
            self._status_label.configure(
                text="Select at least one program to continue.",
                text_color="#B00020",
            )
            return
        # Only call the navigation callback when one was provided.
        if self._on_next is not None:
            self._on_next()

    def _refresh_status(self) -> None:
        """Update the selection counter and enable Next only when valid."""
        count = self.selection_presenter.selection_count()
        # Mirror the presenter's count in the footer ("Selected: X / 5").
        self._status_label.configure(
            text=f"Selected: {count} / {self.selection_presenter.max_programs}",
            text_color="#666666",
        )
        if hasattr(self, "_selection_badge"):
            self._selection_badge.configure(
                text=f"{count} / {self.selection_presenter.max_programs} selected"
            )
        # Disable Next until the selection is valid, so the user can't advance
        # with zero programs chosen.
        self._next_button.configure(
            state="normal" if self.selection_presenter.can_proceed() else "disabled"
        )
