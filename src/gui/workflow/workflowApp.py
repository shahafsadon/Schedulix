from __future__ import annotations

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.async_runner import AsyncScheduleRunner
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
from scheduling.examDateHandler import ExamDateHandler


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
        # The runner is shared: DateManagementScreen drives it for generation;
        # ScheduleNavigationScreen reads is_running to gate threshold controls.
        self._runner = AsyncScheduleRunner()
        self._screen: ctk.CTkFrame | None = None
        self._program_selection: ProgramSelectionPresenter | None = None

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
            )
        )

    def _handle_program_selection_next(self) -> None:
        """Persist the selected programs before leaving the program step."""
        if self._program_selection is None or not self._program_selection.can_proceed():
            return

        self.cache.set_selected_programs(
            self._program_selection.selected_programs
        )
        self.show_date_management()

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
                    on_back=self.show_program_config,
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
                runner=self._runner,
                on_back=self.show_program_config,
                on_generation_success=self.show_output_navigation,
            )
        )

    def _persist_exam_periods(self) -> None:
        """Persist the currently mutated exam-period objects to disk cache."""
        self.cache.set_exam_periods(self.cache.get_exam_periods())

    def show_output_navigation(self) -> None:
        """Show generated schedules with previous/next and export support."""
        self._set_window_title("Schedulix - Generated Schedules")
        schedules = self.cache.get_generated_schedules()

        if not schedules:
            self._set_screen(
                _MessageScreen(
                    self,
                    title="No Generated Schedules",
                    message="Generate schedules before opening the output screen.",
                    on_back=self.show_date_management,
                )
            )
            return

        navigation_presenter = ScheduleNavigationPresenter(schedules)
        export_presenter = ExportPresenter(navigation_presenter)

        self._set_screen(
            ScheduleNavigationScreen(
                self,
                presenter=navigation_presenter,
                export_presenter=export_presenter,
                on_back=self.show_date_management,
                runner=self._runner,
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


class _MessageScreen(ctk.CTkFrame):
    """Small internal screen used between workflow checkpoints."""

    def __init__(
        self,
        master,
        title: str,
        message: str,
        on_back,
    ) -> None:
        super().__init__(master, corner_radius=0)
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
