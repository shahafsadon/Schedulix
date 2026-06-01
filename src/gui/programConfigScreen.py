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

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from gui.programSelectionPresenter import ProgramSelectionPresenter
from gui.programDetailsPresenter import ProgramDetailsPresenter, ProgramDetails


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
        super().__init__(master, corner_radius=0)
        # Two presenters, two responsibilities: selecting vs inspecting.
        self.selection_presenter = selection_presenter
        self.details_presenter = details_presenter
        self._on_next = on_next
        self._on_back = on_back

        # Per-program widgets kept so each row can update independently.
        self._checkbox_vars: dict[str, ctk.BooleanVar] = {}
        self._expanded: dict[str, bool] = {}
        self._detail_frames: dict[str, ctk.CTkFrame] = {}
        self._toggle_buttons: dict[str, ctk.CTkButton] = {}

        self._build()
        self._refresh_status()

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Select Study Programs (up to 5)",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        # Every program row lives in one scrollable column so expanding a row
        # pushes the rows below it downward, as described in section 4.2.
        self._list_frame = ctk.CTkScrollableFrame(self)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        self._list_frame.grid_columnconfigure(0, weight=1)

        programs = self.selection_presenter.available_programs
        if not programs:
            ctk.CTkLabel(
                self._list_frame,
                text="No programs found. Load a courses file first.",
                text_color="#666666",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
        else:
            for program in programs:
                self._build_program_row(program)

        self._build_footer()

    def _build_program_row(self, program_number: str) -> None:
        # A row container holds the header line plus a hidden details frame.
        row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(1, weight=1)

        # (a) Selection checkbox: toggles whether the program goes to scheduling.
        variable = ctk.BooleanVar(
            value=self.selection_presenter.is_selected(program_number)
        )
        checkbox = ctk.CTkCheckBox(
            row,
            text=f"Program {program_number}",
            variable=variable,
            command=lambda current=program_number: self._on_check(current),
        )
        checkbox.grid(row=0, column=0, columnspan=2, sticky="w", padx=(4, 8), pady=4)
        self._checkbox_vars[program_number] = variable

        # (b) Expand/collapse toggle: reveals the program's course details.
        toggle = ctk.CTkButton(
            row,
            text=">",
            width=32,
            fg_color="transparent",
            border_width=1,
            command=lambda current=program_number: self._on_toggle(current),
        )
        toggle.grid(row=0, column=2, sticky="e", padx=(8, 4), pady=4)
        self._toggle_buttons[program_number] = toggle

        # Details frame stays empty and hidden until the row is first expanded.
        details_frame = ctk.CTkFrame(row, fg_color=("#f0f0f0", "#2b2b2b"))
        details_frame.grid_columnconfigure(0, weight=1)
        self._detail_frames[program_number] = details_frame
        self._expanded[program_number] = False

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        footer.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(footer, text="", text_color="#666666")
        self._status_label.grid(row=0, column=0, sticky="w")

        if self._on_back is not None:
            ctk.CTkButton(
                footer,
                text="Back",
                width=90,
                fg_color="transparent",
                border_width=1,
                command=self._on_back,
            ).grid(row=0, column=1, padx=(8, 8))

        self._next_button = ctk.CTkButton(
            footer, text="Next", width=90, command=self._handle_next
        )
        self._next_button.grid(row=0, column=2)

    def _on_check(self, program_number: str) -> None:
        # Ask the selection presenter to apply the change, revert if rejected.
        result = self.selection_presenter.toggle(program_number)
        if not result.accepted:
            self._checkbox_vars[program_number].set(
                self.selection_presenter.is_selected(program_number)
            )
            self._status_label.configure(text=result.message, text_color="#B00020")
            return
        self._refresh_status()

    def _on_toggle(self, program_number: str) -> None:
        # Flip expansion; build details lazily the first time a row is opened.
        expanded = not self._expanded[program_number]
        self._expanded[program_number] = expanded
        frame = self._detail_frames[program_number]

        if expanded:
            if not frame.winfo_children():
                self._fill_details(
                    frame, self.details_presenter.get_details(program_number)
                )
            frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=(24, 4), pady=(0, 6))
            self._toggle_buttons[program_number].configure(text="v")
        else:
            frame.grid_forget()
            self._toggle_buttons[program_number].configure(text=">")

    def _fill_details(self, frame: ctk.CTkFrame, details: ProgramDetails) -> None:
        if details.course_count == 0:
            ctk.CTkLabel(
                frame,
                text="No courses found for this program.",
                text_color="#666666",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=4)
            return

        grid_row = 0
        for group in details.groups:
            ctk.CTkLabel(
                frame,
                text=f"Year {group.year} - {group.semester}",
                font=("Segoe UI", 12, "bold"),
            ).grid(row=grid_row, column=0, sticky="w", padx=8, pady=(6, 2))
            grid_row += 1

            for course in group.courses:
                line = (
                    f"{course.course_number}  |  {course.name}  |  "
                    f"{course.status}  |  {course.evaluation_type}"
                )
                ctk.CTkLabel(frame, text=line, anchor="w").grid(
                    row=grid_row, column=0, sticky="w", padx=20, pady=1
                )
                grid_row += 1

    def _handle_next(self) -> None:
        if not self.selection_presenter.can_proceed():
            self._status_label.configure(
                text="Select at least one program to continue.",
                text_color="#B00020",
            )
            return
        if self._on_next is not None:
            self._on_next()

    def _refresh_status(self) -> None:
        count = self.selection_presenter.selection_count()
        self._status_label.configure(
            text=f"Selected: {count} / {self.selection_presenter.max_programs}",
            text_color="#666666",
        )
        self._next_button.configure(
            state="normal" if self.selection_presenter.can_proceed() else "disabled"
        )