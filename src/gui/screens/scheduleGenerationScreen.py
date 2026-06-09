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
from gui.presenters.schedulingPresenter import GenerationResult, SchedulingPresenter


_PAGE_BG = ("#F3F6FB", "#0B1220")
_SURFACE = ("#FFFFFF", "#151B26")
_SUBTLE_SURFACE = ("#F8FAFC", "#101826")
_BORDER = ("#D8E2F0", "#2D3748")
_TEXT = ("#111827", "#F8FAFC")
_MUTED = ("#5F6368", "#A8A8A8")
_PRIMARY = "#2563EB"
_PRIMARY_HOVER = "#1D4ED8"


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
        super().__init__(master, corner_radius=0, fg_color=_PAGE_BG)
        self.presenter = presenter
        self._runner = runner or AsyncScheduleRunner()
        self._on_back = on_back
        self._on_next = on_next
        self._last_schedule_count = 0

        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_main_card()
        self._build_footer()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Generate Exam Schedules",
            font=("Segoe UI", 24, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Build valid schedule systems from the uploaded data and edited periods.",
            font=("Segoe UI", 13),
            text_color=_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    def _build_main_card(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card,
            text="Scheduling Run",
            font=("Segoe UI", 17, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))

        ctk.CTkLabel(
            card,
            text=(
                "The generator uses selected programs, uploaded exam courses, "
                "and the current exam-period calendar settings."
            ),
            font=("Segoe UI", 12),
            text_color=_MUTED,
            wraplength=840,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))

        status_panel = ctk.CTkFrame(
            card,
            fg_color=_SUBTLE_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        status_panel.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 18))
        status_panel.grid_columnconfigure(0, weight=1)

        self._state_label = ctk.CTkLabel(
            status_panel,
            text="Ready",
            font=("Segoe UI", 26, "bold"),
            text_color=(_PRIMARY, "#93C5FD"),
        )
        self._state_label.grid(row=0, column=0, pady=(42, 4))

        self._status_label = ctk.CTkLabel(
            status_panel,
            text="Click Generate to build schedules.",
            font=("Segoe UI", 13),
            text_color=_MUTED,
            wraplength=760,
            justify="center",
        )
        self._status_label.grid(row=1, column=0, padx=24, pady=(0, 18))

        self._count_label = ctk.CTkLabel(
            status_panel,
            text="No schedules generated in this session yet.",
            font=("Segoe UI", 12),
            text_color=_MUTED,
        )
        self._count_label.grid(row=2, column=0, pady=(0, 36))

        self._generate_button = ctk.CTkButton(
            card,
            text="Generate",
            width=132,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_generate,
        )
        self._generate_button.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 20))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)

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

        self._next_button = ctk.CTkButton(
            footer,
            text="View Results",
            width=124,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
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
                text_color=_MUTED,
            )

    def _show_generation_started(self) -> None:
        """Reflect that the worker accepted a generation task."""
        self._generate_button.configure(state="disabled")
        self._next_button.configure(state="disabled")
        self._state_label.configure(text="Generating...", text_color=(_PRIMARY, "#93C5FD"))
        self._status_label.configure(
            text="Searching for valid exam-system options. You can keep the app open while this runs.",
            text_color=_MUTED,
        )
        self._count_label.configure(text="Working in the background.")

    def _show_generation_result(self, result: GenerationResult) -> None:
        """Render the generation result returned by the worker."""
        self._last_schedule_count = result.schedule_count
        color = "#147A39" if result.success else "#B00020"
        state = "Ready to Review" if result.success and result.schedule_count > 0 else "Needs Attention"

        self._state_label.configure(text=state, text_color=color)
        self._status_label.configure(text=result.message, text_color=color)
        self._count_label.configure(
            text=(
                f"{result.schedule_count} schedule system(s) generated."
                if result.success
                else "No schedules were stored."
            )
        )

        self._next_button.configure(
            state="normal" if result.success and result.schedule_count > 0 else "disabled"
        )
        self._generate_button.configure(state="normal")

    def _show_generation_error(self, error: Exception) -> None:
        """Render unexpected worker failures without crashing the GUI."""
        self._state_label.configure(text="Failed", text_color="#B00020")
        self._status_label.configure(
            text=f"Schedule generation failed unexpectedly: {type(error).__name__}.",
            text_color="#B00020",
        )
        self._count_label.configure(text="No schedules were stored.")
        self._next_button.configure(state="disabled")
        self._generate_button.configure(state="normal")

    def _handle_next(self) -> None:
        """Move to the output step when generated schedules are available."""
        if self._last_schedule_count <= 0:
            self._status_label.configure(
                text="Generate at least one schedule before opening the output screen.",
                text_color="#B00020",
            )
            return

        if self._on_next is not None:
            self._on_next()
