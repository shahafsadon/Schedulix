"""Program-selection screen for the Version 2.0 GUI wizard (SCRUM-122).

This is a passive View in the MVP pattern: it builds the widgets, forwards user
actions to the ProgramSelectionPresenter, and updates itself from the
presenter's answers. It contains no selection logic of its own.
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


class ProgramSelectionScreen(ctk.CTkFrame):
    """Lets the user choose up to five study programs from a scrollable list."""

    def __init__(
        self,
        master,
        presenter: ProgramSelectionPresenter,
        on_next: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, corner_radius=0)
        # The presenter holds all selection logic; the screen only displays it.
        self.presenter = presenter
        # Optional navigation callbacks supplied by the wizard shell later.
        self._on_next = on_next
        self._on_back = on_back

        # Keep one checkbox + its bound variable per program so the screen can
        # revert a rejected click and read the current visual state.
        self._checkboxes: dict[str, ctk.CTkCheckBox] = {}
        self._variables: dict[str, ctk.BooleanVar] = {}

        self._build()
        self._refresh_status()

    def _build(self) -> None:
        # Let the scrollable list expand while header/footer stay fixed height.
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Select Study Programs (up to 5)",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        # One checkbox per available program, inside a scrollable container so
        # long program lists stay usable on a small window.
        self._list_frame = ctk.CTkScrollableFrame(self)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        self._list_frame.grid_columnconfigure(0, weight=1)

        if not self.presenter.available_programs:
            ctk.CTkLabel(
                self._list_frame,
                text="No programs found. Load a courses file first.",
                text_color="#666666",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
        else:
            for row_index, program in enumerate(self.presenter.available_programs):
                variable = ctk.BooleanVar(value=self.presenter.is_selected(program))
                checkbox = ctk.CTkCheckBox(
                    self._list_frame,
                    text=program,
                    variable=variable,
                    command=lambda current=program: self._on_toggle(current),
                )
                checkbox.grid(row=row_index, column=0, sticky="w", padx=8, pady=4)
                self._checkboxes[program] = checkbox
                self._variables[program] = variable

        # Footer: selection counter + navigation buttons.
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
            footer,
            text="Next",
            width=90,
            command=self._handle_next,
        )
        self._next_button.grid(row=0, column=2)

    def _on_toggle(self, program_number: str) -> None:
        # Ask the presenter to apply the change, then keep or revert the click.
        result = self.presenter.toggle(program_number)

        if not result.accepted:
            # Revert the checkbox to the presenter's real state and warn user.
            self._variables[program_number].set(
                self.presenter.is_selected(program_number)
            )
            self._status_label.configure(text=result.message, text_color="#B00020")
            return

        self._refresh_status()

    def _handle_next(self) -> None:
        # Block navigation until the selection is valid; the presenter decides.
        if not self.presenter.can_proceed():
            self._status_label.configure(
                text="Select at least one program to continue.",
                text_color="#B00020",
            )
            return

        if self._on_next is not None:
            self._on_next()

    def _refresh_status(self) -> None:
        # Update the counter and enable Next only when the selection is valid.
        count = self.presenter.selection_count()
        self._status_label.configure(
            text=f"Selected: {count} / {self.presenter.max_programs}",
            text_color="#666666",
        )
        self._next_button.configure(
            state="normal" if self.presenter.can_proceed() else "disabled"
        )