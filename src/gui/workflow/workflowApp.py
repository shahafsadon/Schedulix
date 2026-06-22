from __future__ import annotations

from importlib import import_module
from inspect import Parameter, signature
from typing import Any

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.cache_manager import CacheManager
from gui.presenters.dateManagementPresenter import DateManagementPresenter
from gui.screens.dateManagementScreen import DateManagementScreen
from gui.presenters.exportPresenter import ExportPresenter
from gui.screens.fileUploadScreen import FileUploadScreen
from gui.presenters.programDetailsPresenter import ProgramDetailsPresenter
from gui.screens.programConfigScreen import ProgramConfigScreen
from gui.presenters.programSelectionPresenter import ProgramSelectionPresenter
from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter
from gui.screens.scheduleNavigationScreen import ScheduleNavigationScreen
from gui.presenters.schedulingPresenter import SchedulingPresenter
from gui.services.uploadService import FileUploadService
from gui.services.uploadedDataExportService import UploadedDataExportService
from gui.presenters.uploadedDataPresenter import UploadedDataPresenter
from gui.screens.themeToggle import (
    THEME_BUTTON_WIDTH,
    ThemeButtonText,
    ThemeToggleCallback,
    current_theme_button_text,
    handle_theme_toggle,
    theme_button_text_for_mode,
)
from scheduling.examDateHandler import ExamDateHandler
from constraint_settings import SchedulingConstraintSettings


class SchedulixWorkflow(ctk.CTkFrame):
    """Owns the Version 2.0 wizard flow and swaps screens in one window."""

    def __init__(
        self,
        master,
        cache_manager: CacheManager | None = None,
    ) -> None:
        super().__init__(master, corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.cache = cache_manager or CacheManager()
        self.upload_service = FileUploadService(cache_manager=self.cache)
        self.data_presenter = UploadedDataPresenter(
            cache_manager=self.cache,
            uploaded_data=self.upload_service.get_uploaded_data(),
        )
        self.uploaded_export_service = UploadedDataExportService(
            cache_manager=self.cache,
            uploaded_data=self.upload_service.get_uploaded_data(),
        )
        self._screen: ctk.CTkFrame | None = None
        self._program_selection: ProgramSelectionPresenter | None = None
        self._settings_presenter: Any | None = None
        self._theme_mode = self._current_theme_mode()

        self.show_upload()

    def show_upload(self) -> None:
        """Show the input upload and preview step."""
        self._set_window_title("Schedulix - File Upload")
        self._set_screen(
            FileUploadScreen(
                self,
                upload_service=self.upload_service,
                data_presenter=self.data_presenter,
                export_service=self.uploaded_export_service,
                on_next=self.show_program_config,
                **self._theme_kwargs(),
            )
        )

    def show_program_config(self) -> None:
        """Show the study-program selection and details step."""
        self._set_window_title("Schedulix - Program Selection")

        courses = self.cache.get_courses()
        selection_presenter = ProgramSelectionPresenter(
            courses,
            selected_programs=self.cache.get_selected_programs(),
        )
        details_presenter = ProgramDetailsPresenter(courses)
        self._program_selection = selection_presenter

        self._set_screen(
            ProgramConfigScreen(
                self,
                selection_presenter=selection_presenter,
                details_presenter=details_presenter,
                on_back=self.show_upload,
                on_next=self._handle_program_selection_next,
                **self._theme_kwargs(),
            )
        )

    def _handle_program_selection_next(self) -> None:
        """Persist the selected programs before leaving the program step."""
        if self._program_selection is None or not self._program_selection.can_proceed():
            return

        self.cache.set_selected_programs(
            self._program_selection.selected_programs
        )
        self.show_scheduling_settings()

    def show_scheduling_settings(self) -> None:
        """Show the Part 3 threshold-settings step before date management."""
        self._set_window_title("Schedulix - Scheduling Settings")

        components = self._load_scheduling_settings_components()
        if components is None:
            self._set_screen(
                _MessageScreen(
                    self,
                    title="Scheduling Settings Unavailable",
                    message=(
                        "The scheduling settings screen is not available in "
                        "this checkout. Merge the settings screen and "
                        "presenter changes before opening this step."
                    ),
                    on_back=self.show_program_config,
                    **self._theme_kwargs(),
                )
            )
            return

        presenter_cls, screen_cls = components
        self._settings_presenter = presenter_cls(cache_manager=self.cache)

        self._set_screen(
            screen_cls(
                self,
                **self._settings_screen_kwargs(
                    screen_cls,
                    self._settings_presenter,
                ),
            )
        )

    def _handle_settings_next(
        self,
        settings: SchedulingConstraintSettings | None = None,
    ) -> None:
        """Persist valid settings, then continue to Date Management."""
        if settings is not None:
            self._save_constraint_settings_if_changed(settings)
            self.show_date_management()
            return

        if self._settings_presenter is None:
            return

        save = getattr(self._settings_presenter, "save", None)
        if save is None:
            self.show_date_management()
            return

        result = save()
        if getattr(result, "success", False):
            self.show_date_management()

    def _save_constraint_settings_if_changed(
        self,
        settings: SchedulingConstraintSettings,
    ) -> None:
        """Avoid invalidating generated schedules when settings did not change."""
        if settings != self.cache.get_constraint_settings():
            self.cache.set_constraint_settings(settings)

    @staticmethod
    def _load_scheduling_settings_components():
        """Import settings components only when the workflow reaches the step."""
        try:
            presenter_module = import_module(
                "gui.presenters.schedulingSettingsPresenter"
            )
            screen_module = import_module(
                "gui.screens.schedulingSettingsScreen"
            )
        except ModuleNotFoundError:
            return None

        return (
            presenter_module.SchedulingSettingsPresenter,
            screen_module.SchedulingSettingsScreen,
        )

    def _settings_screen_kwargs(
        self,
        screen_cls,
        presenter,
    ) -> dict[str, Any]:
        """Build constructor kwargs across the screen/presenter transition."""
        kwargs: dict[str, Any] = {
            "on_back": self.show_program_config,
            "on_next": self._handle_settings_next,
        }

        if self._constructor_accepts(screen_cls, "presenter"):
            kwargs["presenter"] = presenter
        elif self._constructor_accepts(screen_cls, "settings_presenter"):
            kwargs["settings_presenter"] = presenter
        else:
            kwargs["initial_settings"] = self.cache.get_constraint_settings()

        if self._constructor_accepts(screen_cls, "on_theme_toggle"):
            kwargs["on_theme_toggle"] = self.toggle_theme
        if self._constructor_accepts(screen_cls, "theme_button_text"):
            kwargs["theme_button_text"] = self.theme_button_text

        return kwargs

    @staticmethod
    def _constructor_accepts(
        cls,
        parameter_name: str,
    ) -> bool:
        parameters = signature(cls.__init__).parameters.values()
        return any(
            parameter.name == parameter_name
            or parameter.kind == Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def show_date_management(self) -> None:
        """Show the calendar editing step for all uploaded exam periods."""
        self._set_window_title("Schedulix - Date Management")
        exam_periods = self.cache.get_exam_periods()

        if not exam_periods:
            self._set_screen(
                _MessageScreen(
                    self,
                    title="No Exam Periods Loaded",
                    message="Go back and load an exam-periods file before editing dates.",
                    on_back=self.show_scheduling_settings,
                    **self._theme_kwargs(),
                )
            )
            return

        date_handler = ExamDateHandler()
        presenters = [
            DateManagementPresenter(
                exam_period=exam_period,
                date_handler=date_handler,
                cache_manager=self.cache,
                courses=self.cache.get_courses(),
                exam_periods=exam_periods,
                on_change=self._persist_exam_periods,
            )
            for exam_period in exam_periods
        ]

        self._set_screen(
            DateManagementScreen(
                self,
                presenter=presenters[0],
                period_presenters=presenters,
                scheduling_presenter=SchedulingPresenter(self.cache),
                on_back=self.show_scheduling_settings,
                on_generation_success=self.show_output_navigation,
                **self._theme_kwargs(),
            )
        )

    def _persist_exam_periods(self) -> None:
        """Persist the currently mutated exam-period objects to disk cache."""
        self.cache.set_exam_periods(self.cache.get_exam_periods())

    def show_output_navigation(self) -> None:
        """Show generated schedules with previous/next and export support."""
        self._set_window_title("Schedulix - Generated Schedules")
        schedules = self.cache.get_generated_schedules()
        ranked_schedules = self.cache.get_ranked_schedules()

        if not schedules:
            self._set_screen(
                _MessageScreen(
                    self,
                    title="No Generated Schedules",
                    message="Generate schedules before opening the output screen.",
                    on_back=self.show_date_management,
                    **self._theme_kwargs(),
                )
            )
            return

        # Prefer ranked wrappers when metrics were calculated; fall back to the
        # raw systems so older cached sessions still open normally.
        # Pass the shared cache so apply_ranking() can persist ranking settings
        # and the new display order to disk (SCRUM-184).
        navigation_presenter = ScheduleNavigationPresenter(
            ranked_schedules or schedules,
            cache_manager=self.cache,
        )
        export_presenter = ExportPresenter(navigation_presenter)

        self._set_screen(
            ScheduleNavigationScreen(
                self,
                presenter=navigation_presenter,
                export_presenter=export_presenter,
                on_back=self.show_date_management,
                **self._theme_kwargs(),
            )
        )

    def _set_screen(self, screen: ctk.CTkFrame) -> None:
        if self._screen is not None:
            self._screen.destroy()
        self._screen = screen
        self._screen.grid(row=0, column=0, sticky="nsew")

    def _set_window_title(self, title: str) -> None:
        window = self.winfo_toplevel()
        if hasattr(window, "title"):
            window.title(title)

    def toggle_theme(self) -> str:
        """Switch the whole GUI between light and dark mode."""
        self._theme_mode = "Light" if self._theme_mode == "Dark" else "Dark"
        ctk.set_appearance_mode(self._theme_mode)
        return self._theme_mode

    def theme_button_text(self) -> str:
        """Return the next theme action shown on every screen."""
        return theme_button_text_for_mode(self._theme_mode)

    def _theme_kwargs(self) -> dict[str, Any]:
        """Pass the shared theme toggle to a screen."""
        return {
            "on_theme_toggle": self.toggle_theme,
            "theme_button_text": self.theme_button_text,
        }

    @staticmethod
    def _current_theme_mode() -> str:
        """Read the active customTkinter mode when the API exists."""
        get_mode = getattr(ctk, "get_appearance_mode", None)
        if callable(get_mode) and get_mode() == "Dark":
            return "Dark"
        return "Light"


class _MessageScreen(ctk.CTkFrame):
    """Small internal screen used between workflow checkpoints."""

    def __init__(
        self,
        master,
        title: str,
        message: str,
        on_back,
        on_theme_toggle: ThemeToggleCallback | None = None,
        theme_button_text: ThemeButtonText = None,
    ) -> None:
        super().__init__(master, corner_radius=0)
        self._on_theme_toggle = on_theme_toggle
        self._theme_button_text = theme_button_text
        self._theme_button = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0)

        ctk.CTkLabel(
            body,
            text=title,
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, padx=24, pady=(24, 8))

        ctk.CTkLabel(
            body,
            text=message,
            wraplength=520,
            justify="center",
        ).grid(row=1, column=0, padx=24, pady=(0, 18))

        ctk.CTkButton(
            body,
            text="Back",
            width=100,
            command=on_back,
        ).grid(row=2, column=0, pady=(0, 24))

        if self._on_theme_toggle is not None:
            # Button text tells the user which mode the click will open.
            self._theme_button = ctk.CTkButton(
                body,
                text=current_theme_button_text(self._theme_button_text),
                width=THEME_BUTTON_WIDTH,
                command=lambda: handle_theme_toggle(
                    self._on_theme_toggle,
                    self._theme_button,
                    self._theme_button_text,
                ),
            )
            self._theme_button.grid(row=3, column=0, pady=(0, 24))
