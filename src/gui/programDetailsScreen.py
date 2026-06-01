"""Program-details screen for the Version 2.0 GUI wizard (SCRUM-123).

Passive MVP View: it asks the ProgramDetailsPresenter for a program's grouped
course list and renders it as an expandable section per program. It contains no
data logic of its own.
"""
from __future__ import annotations

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from gui.programDetailsPresenter import ProgramDetailsPresenter, ProgramDetails


class ProgramDetailsScreen(ctk.CTkFrame):
    """Shows expandable detail panels for each selected study program."""

    def __init__(
        self,
        master,
        presenter: ProgramDetailsPresenter,
        selected_programs: list[str],
    ) -> None:
        super().__init__(master, corner_radius=0)
        # The presenter computes per-program details; the screen only displays.
        self.presenter = presenter
        # The programs chosen on the previous step (SCRUM-122).
        self.selected_programs = selected_programs
        # Track which program panels are currently expanded.
        self._expanded: dict[str, bool] = {}
        # Keep references to the body frames so they can be shown/hidden.
        self._bodies: dict[str, ctk.CTkFrame] = {}

        self._build()

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Selected Programs - Details",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        # All program panels live in one scrollable column.
        container = ctk.CTkScrollableFrame(self)
        container.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        container.grid_columnconfigure(0, weight=1)

        if not self.selected_programs:
            ctk.CTkLabel(
                container,
                text="No programs selected.",
                text_color="#666666",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return

        # One expandable panel per selected program.
        for row_index, program_number in enumerate(self.selected_programs):
            details = self.presenter.get_details(program_number)
            self._build_program_panel(container, row_index, details)

    def _build_program_panel(
        self,
        container: ctk.CTkFrame,
        row_index: int,
        details: ProgramDetails,
    ) -> None:
        panel = ctk.CTkFrame(container)
        panel.grid(row=row_index, column=0, sticky="ew", pady=6)
        panel.grid_columnconfigure(0, weight=1)

        program_number = details.program_number
        self._expanded.setdefault(program_number, False)

        # Header button: program metadata + toggles the body open/closed.
        header = ctk.CTkButton(
            panel,
            text=self._header_text(details, expanded=False),
            anchor="w",
            fg_color="transparent",
            text_color=("#1a1a1a", "#e5e5e5"),
            hover_color=("#dcdcdc", "#333333"),
            command=lambda current=program_number: self._toggle(current),
        )
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        self._headers = getattr(self, "_headers", {})
        self._headers[program_number] = (header, details)

        # Body: the grouped course list, hidden until the panel is expanded.
        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.grid_columnconfigure(0, weight=1)
        self._bodies[program_number] = body
        self._fill_body(body, details)

    def _fill_body(self, body: ctk.CTkFrame, details: ProgramDetails) -> None:
        if details.course_count == 0:
            ctk.CTkLabel(
                body,
                text="No courses found for this program.",
                text_color="#666666",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=4)
            return

        row = 0
        for group in details.groups:
            # One sub-header per (year, semester) slot.
            ctk.CTkLabel(
                body,
                text=f"Year {group.year} - {group.semester}",
                font=("Segoe UI", 12, "bold"),
            ).grid(row=row, column=0, sticky="w", padx=12, pady=(8, 2))
            row += 1

            # One readable line per course: number, name, requirement, eval.
            for course in group.courses:
                line = (
                    f"{course.course_number}  |  {course.name}  |  "
                    f"{course.status}  |  {course.evaluation_type}"
                )
                ctk.CTkLabel(body, text=line, anchor="w").grid(
                    row=row, column=0, sticky="w", padx=24, pady=1
                )
                row += 1

    def _toggle(self, program_number: str) -> None:
        # Flip the expanded flag and show or hide the body accordingly.
        expanded = not self._expanded.get(program_number, False)
        self._expanded[program_number] = expanded

        body = self._bodies[program_number]
        if expanded:
            body.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        else:
            body.grid_forget()

        header, details = self._headers[program_number]
        header.configure(text=self._header_text(details, expanded=expanded))

    @staticmethod
    def _header_text(details: ProgramDetails, expanded: bool) -> str:
        # A small caret hints whether the panel is open, plus quick metadata.
        caret = "v" if expanded else ">"
        plural = "s" if details.course_count != 1 else ""
        return (
            f"{caret}  Program {details.program_number}  "
            f"({details.course_count} course{plural})"
        )