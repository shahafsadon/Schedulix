from __future__ import annotations

from typing import Callable

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.async_runner import AsyncScheduleRunner
from gui.schedulingPresenter import GenerationResult
from gui.schedulingPresenter import SchedulingPresenter


class ScheduleGenerationScreen(ctk.CTkFrame):
    """Screen that runs schedule generation from the cached workflow data."""

    def __init__(
        self,
        master,
        presenter: SchedulingPresenter,
        runner: AsyncScheduleRunner | None = None,
        on_back: Callable[[], None] | None = None,
        on_next: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, corner_radius=0)
        self.presenter = presenter
        self._runner = runner or AsyncScheduleRunner()
        self._on_back = on_back
        self._on_next = on_next

        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Generate Exam Schedules",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            text=(
                "Ready to generate valid exam-system options from the uploaded "
                "courses, selected programs, and edited exam periods."
            ),
            wraplength=760,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self._status_label = ctk.CTkLabel(
            body,
            text="Click Generate to build schedules.",
            text_color="#666666",
            anchor="w",
        )
        self._status_label.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self._generate_button = ctk.CTkButton(
            body,
            text="Generate",
            width=120,
            command=self._handle_generate,
        )
        self._generate_button.grid(row=2, column=0, sticky="w")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        footer.grid_columnconfigure(0, weight=1)

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
            text="View Results",
            width=120,
            command=self._handle_next,
            state="disabled",
        )
        self._next_button.grid(row=0, column=2)

    def _handle_generate(self) -> None:
        """Generate schedules in the background and update the screen later."""
        accepted = self._runner.run(
            task=self.presenter.generate,
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
            self._status_label.configure(
                text="Schedule generation is already running.",
                text_color="#666666",
            )

    def _show_generation_started(self) -> None:
        """Reflect that the worker accepted a generation task."""
        self._generate_button.configure(state="disabled")
        self._next_button.configure(state="disabled")
        self._status_label.configure(
            text="Generating schedules...",
            text_color="#666666",
        )

    def _show_generation_result(self, result: GenerationResult) -> None:
        """Render the generation result returned by the worker."""
        color = "#147A39" if result.success else "#B00020"
        self._status_label.configure(
            text=result.message,
            text_color=color,
        )

        if result.success and result.schedule_count > 0:
            self._next_button.configure(state="normal")
        else:
            self._next_button.configure(state="disabled")

        self._generate_button.configure(state="normal")

    def _show_generation_error(self, error: Exception) -> None:
        """Render unexpected worker failures without crashing the GUI."""
        self._status_label.configure(
            text=f"Schedule generation failed unexpectedly: {type(error).__name__}.",
            text_color="#B00020",
        )
        self._next_button.configure(state="disabled")
        self._generate_button.configure(state="normal")

    def _handle_next(self) -> None:
        """Move to the output step when generated schedules are available."""
        if self._on_next is not None:
            self._on_next()
