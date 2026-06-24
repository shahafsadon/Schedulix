#Path is used to save the file path that the user selected.
from pathlib import Path
#filedialog opens the regular Windows file picker.
from tkinter import filedialog
from typing import Callable
#customtkinter is the GUI library used by this screen.
try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from fileReader.baseFileReader import FileReaderType
from gui.services.uploadService import FileUploadService, UploadMode, UploadResult
from gui.services.uploadedDataExportService import UploadedDataExportService, ExportResult
from gui.presenters.uploadedDataPresenter import UploadedDataPresenter, UploadedDataSnapshot
from gui.screens.themeToggle import (
    THEME_BUTTON_WIDTH,
    ThemeButtonText,
    ThemeToggleCallback,
    current_theme_button_text,
    handle_theme_toggle,
)


#this class builds the file upload screen in the GUI.
class FileUploadScreen(ctk.CTkFrame):
    """
    File upload screen for the Version 2.0 GUI workflow.

    The screen lets the user choose the three required input files, either
    replace or append each dataset, validates files through the existing
    readers, exports parsed datasets, and displays upload/export feedback.
    """

    def __init__(
        self,
        master,
        upload_service: FileUploadService | None = None,
        data_presenter: UploadedDataPresenter | None = None,
        export_service: UploadedDataExportService | None = None,
        on_next: Callable[[], None] | None = None,
        on_theme_toggle: ThemeToggleCallback | None = None,
        theme_button_text: ThemeButtonText = None,
    ) -> None:
        super().__init__(master, corner_radius=0)
        #the screen talks to this service instead of calling file readers directly
        #this keeps GUI code focused on display and user actions while the service handles validation, parsing, and caching logic.
        self.upload_service = upload_service or FileUploadService()
        self.data_presenter = data_presenter or UploadedDataPresenter(
            cache_manager=self.upload_service.cache_manager,
            uploaded_data=self.upload_service.get_uploaded_data(),
        )
        self.export_service = export_service or UploadedDataExportService(
            cache_manager=self.upload_service.cache_manager,
            uploaded_data=self.upload_service.get_uploaded_data(),
        )
        self._on_next = on_next
        self._on_theme_toggle = on_theme_toggle
        self._theme_button_text = theme_button_text

        #keep labels and paths by file type so each upload row updated independently and the export func know which data to use.
        self.status_labels: dict[FileReaderType, ctk.CTkLabel] = {}
        self.preview_metric_labels: dict[str, ctk.CTkLabel] = {}
        self.selected_paths: dict[FileReaderType, Path] = {}
        self._continue_button: ctk.CTkButton | None = None
        self._theme_button: ctk.CTkButton | None = None

        self._build()

    def _build(self) -> None:
        #the card layout expand when the window is resized.
        self.configure(fg_color=("#F3F6FB", "#0B1220"))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1, minsize=320)

        #main colors used by the screen.
        primary_color = "#2563EB"
        primary_hover = "#1D4ED8"
        title_color = ("#1D4ED8", "#60A5FA")
        card_color = ("#FFFFFF", "#151B26")
        card_border_color = ("#D8E2F0", "#2D3748")
        muted_text_color = ("#5F6368", "#A8A8A8")
        ghost_text_color = ("#1D4ED8", "#93C5FD")
        ghost_border_color = ("#B8C0CC", "#3F3F46")

        #header frame holds the logo, title, and version badge.
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(12, 10))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=1)

        if self._on_theme_toggle is not None:
            # Button text tells the user which mode the click will open.
            self._theme_button = ctk.CTkButton(
                header,
                text=current_theme_button_text(self._theme_button_text),
                width=THEME_BUTTON_WIDTH,
                fg_color="transparent",
                border_width=1,
                border_color=ghost_border_color,
                text_color=ghost_text_color,
                hover_color=("#DCE8FF", "#1E293B"),
                command=self._handle_theme_toggle,
            )
            self._theme_button.grid(row=0, column=0, sticky="nw", pady=(2, 0))

        #brand frame keeps the SX logo near the app title.
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=1)

        #SX is the small group logo shown near the title.
        brand_mark = ctk.CTkLabel(
            brand,
            text="SX",
            width=74,
            height=56,
            fg_color=("#1E3A8A", "#1E3A8A"),
            corner_radius=18,
            font=("Bahnschrift SemiBold", 22, "bold"),
            text_color="#EAF2FF",
            anchor="center",
        )
        brand_mark.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 14))

        # Main app title.
        ctk.CTkLabel(
            brand,
            text="Schedulix",
            font=("Segoe UI", 31, "bold"),
            text_color=title_color,
            anchor="center",
        ).grid(row=0, column=1, sticky="w")

        #short sentence that explains the screen goal.
        ctk.CTkLabel(
            brand,
            text="Smart exam scheduling dashboard",
            font=("Segoe UI", 12),
            text_color=muted_text_color,
            anchor="center",
        ).grid(row=1, column=1, sticky="w")

        #small badge that shows this is Version 2.0.
        version_badge = ctk.CTkFrame(
            header,
            fg_color=("#E8F1FF", "#111D33"),
            border_width=1,
            border_color=("#BFDBFE", "#2F4D7C"),
            corner_radius=18,
        )
        version_badge.grid(row=0, column=2, sticky="ne", pady=(2, 0))

        #text inside the version badge.
        ctk.CTkLabel(
            version_badge,
            text="Version 2.0",
            font=("Segoe UI", 11, "bold"),
            text_color=ghost_text_color,
            padx=10,
            pady=4,
        ).grid(row=0, column=0)

        #subtitle under the main title.
        ctk.CTkLabel(
            header,
            text="Load, validate, preview, and export your scheduling data.",
            font=("Segoe UI", 12),
            text_color=muted_text_color,
        ).grid(row=1, column=0, columnspan=3, pady=(6, 0))

        #card that contains the three upload rows.
        upload_card = ctk.CTkFrame(
            self,
            fg_color=card_color,
            border_width=1,
            border_color=card_border_color,
            corner_radius=10,
        )
        upload_card.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        upload_card.grid_columnconfigure(1, weight=1)

        #header area inside the upload card.
        upload_header = ctk.CTkFrame(upload_card, fg_color="transparent")
        upload_header.grid(
            row=0,
            column=0,
            columnspan=5,
            sticky="ew",
            padx=20,
            pady=(12, 6),
        )
        upload_header.grid_columnconfigure(0, weight=1)
        upload_header.grid_columnconfigure(2, weight=1)

        # title of the upload card.
        ctk.CTkLabel(
            upload_header,
            text="Input Control Center",
            height=30,
            font=("Segoe UI Semibold", 17, "bold"),
            text_color=("#111827", "#F1F5F9"),
            anchor="center",
        ).grid(row=0, column=0, columnspan=3, sticky="ew")

        # small badge that reminds the user how many files are needed.
        ctk.CTkLabel(
            upload_header,
            text="3 required files",
            font=("Segoe UI", 11, "bold"),
            fg_color=("#E8F1FF", "#1E293B"),
            text_color=ghost_text_color,
            corner_radius=14,
            padx=10,
            pady=4,
        ).grid(row=0, column=2, sticky="e")

        #small label above the upload rows.
        ctk.CTkLabel(
            upload_card,
            text="Load Input Files",
            font=("Segoe UI", 13),
            text_color=muted_text_color,
            anchor="w",
        ).grid(row=1, column=0, columnspan=5, sticky="ew", padx=20, pady=(0, 4))

        #these are the three input files that the system needs.
        rows = [
            (FileReaderType.COURSES, "Courses file"),
            (FileReaderType.PROGRAMS, "Programs file"),
            (FileReaderType.EXAM_PERIODS, "Exam periods file"),
        ]

        #build one upload row for every required Version 2.0 input file.
        for row_index, (file_type, label_text) in enumerate(rows, start=2):
            #this label shows the type of file in the row.
            ctk.CTkLabel(
                upload_card,
                text=label_text,
                font=("Segoe UI", 13, "bold"),
                anchor="w",
            ).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(20, 14),
                pady=6,
            )

            # this label shows the upload result for the row.
            status = ctk.CTkLabel(
                upload_card,
                text="No file loaded",
                text_color=muted_text_color,
                anchor="w",
                justify="left",
            )
            status.grid(row=row_index, column=1, sticky="ew", padx=(0, 14), pady=6)
            self.status_labels[file_type] = status

            # replace loads a new file and replaces old data.
            ctk.CTkButton(
                upload_card,
                text="Replace",
                width=96,
                fg_color=primary_color,
                hover_color=primary_hover,
                #bind the current file type so every button uploads the correct reader instead of all buttons using last row.
                command=lambda current_type=file_type: self._browse(
                    current_type,
                    UploadMode.REPLACE,
                ),
            ).grid(row=row_index, column=2, sticky="e", padx=(0, 10), pady=6)

            # Append adds the new file data to the current data.
            ctk.CTkButton(
                upload_card,
                text="Append",
                width=92,
                fg_color="transparent",
                border_width=1,
                border_color=ghost_border_color,
                text_color=ghost_text_color,
                hover_color=("#DCE8FF", "#1E293B"),
                command=lambda current_type=file_type: self._browse(
                    current_type,
                    UploadMode.APPEND,
                ),
            ).grid(row=row_index, column=3, sticky="e", padx=(0, 10), pady=6)

            #export saves the uploaded data back to a text file.
            ctk.CTkButton(
                upload_card,
                text="Export",
                width=92,
                fg_color="transparent",
                border_width=1,
                border_color=ghost_border_color,
                text_color=ghost_text_color,
                hover_color=("#DCE8FF", "#1E293B"),
                command=lambda current_type=file_type: self._export(current_type),
            ).grid(row=row_index, column=4, sticky="e", padx=(0, 20), pady=6)

        #divider line between the upload rows and status messages.
        ctk.CTkFrame(
            upload_card,
            height=1,
            fg_color=("#D1D5DB", "#3F3F46"),
        ).grid(row=5, column=0, columnspan=5, sticky="ew", padx=20, pady=(4, 8))

        #this label summarizes whether all required files are ready.
        self.ready_label = ctk.CTkLabel(
            upload_card,
            text="Load all required files to continue.",
            text_color=muted_text_color,
            anchor="w",
        )
        self.ready_label.grid(
            row=6,
            column=0,
            columnspan=5,
            sticky="ew",
            padx=20,
            pady=(0, 4),
        )

        self.export_status_label = ctk.CTkLabel(
            upload_card,
            text="Export status will appear here.",
            text_color=muted_text_color,
            anchor="w",
        )
        self.export_status_label.grid(
            row=7,
            column=0,
            columnspan=5,
            sticky="ew",
            padx=20,
            pady=(0, 12),
        )

        if self._on_next is not None:
            footer = ctk.CTkFrame(upload_card, fg_color="transparent")
            footer.grid(row=8, column=0, columnspan=5, sticky="ew", padx=20, pady=(0, 16))
            footer.grid_columnconfigure(0, weight=1)

            self._continue_button = ctk.CTkButton(
                footer,
                text="Continue",
                width=120,
                fg_color=primary_color,
                hover_color=primary_hover,
                command=self._handle_next,
            )
            self._continue_button.grid(row=0, column=1, sticky="e")

        self._build_preview()
        self._refresh_upload_row_statuses()
        self._refresh_ready_label()
        self._refresh_preview()

    def _build_preview(self) -> None:
        """Build the parsed-data preview area and refresh action."""
        # card that contains the preview title, metrics, and text area.
        preview_card = ctk.CTkFrame(
            self,
            fg_color=("#FFFFFF", "#151B26"),
            border_width=1,
            border_color=("#D8E2F0", "#2D3748"),
            corner_radius=10,
        )
        preview_card.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 16))
        preview_card.grid_columnconfigure(0, weight=1)
        preview_card.grid_rowconfigure(2, weight=1, minsize=260)

        #header row for the preview card.
        header = ctk.CTkFrame(preview_card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(2, weight=1)

        #title of the preview card.
        ctk.CTkLabel(
            header,
            text="Uploaded Data Preview",
            height=30,
            font=("Segoe UI Semibold", 17, "bold"),
            text_color=("#111827", "#F1F5F9"),
            anchor="center",
        ).grid(row=0, column=0, columnspan=3, sticky="ew")

        #refresh redraws the preview from the current uploaded data.
        ctk.CTkButton(
            header,
            text="Refresh",
            width=96,
            fg_color="transparent",
            border_width=1,
            border_color=("#B8C0CC", "#3F3F46"),
            text_color=("#1D4ED8", "#93C5FD"),
            hover_color=("#DCE8FF", "#1E293B"),
            command=self._refresh_preview,
        ).grid(row=0, column=2, sticky="e")

        #row that shows quick numbers about the uploaded data.
        metrics = ctk.CTkFrame(preview_card, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        for column_index in range(4):
            metrics.grid_columnconfigure(column_index, weight=1)

        #build the four preview summary boxes.
        self._build_preview_metric(metrics, 0, "courses", "Courses")
        self._build_preview_metric(metrics, 1, "programs", "Programs")
        self._build_preview_metric(metrics, 2, "periods", "Periods")
        self._build_preview_metric(metrics, 3, "ready", "Status")

        #textbox shows the detailed preview of all uploaded data.
        self.preview_textbox = ctk.CTkTextbox(
            preview_card,
            height=300,
            font=("Segoe UI", 13),
            wrap="word",
            fg_color=("#F8FAFC", "#101826"),
            text_color=("#1F2937", "#E5E7EB"),
            border_width=0,
            border_spacing=12,
            corner_radius=8,
            scrollbar_button_color=("#CBD5E1", "#334155"),
            scrollbar_button_hover_color=("#94A3B8", "#475569"),
        )
        self.preview_textbox.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=20,
            pady=(0, 16),
        )

    def _build_preview_metric(
        self,
        master: ctk.CTkFrame,
        column_index: int,
        key: str,
        label_text: str,
    ) -> None:
        """Build one small dashboard metric above the textual preview."""
        #metric frame is one small box in the preview summary row.
        metric = ctk.CTkFrame(
            master,
            fg_color=("#F3F7FF", "#111827"),
            border_width=1,
            border_color=("#D8E2F0", "#2D3748"),
            corner_radius=8,
        )
        metric.grid(
            row=0,
            column=column_index,
            sticky="ew",
            padx=(0 if column_index == 0 else 8, 0),
        )

        #metric name, for example Courses or Programs.
        ctk.CTkLabel(
            metric,
            text=label_text,
            font=("Segoe UI", 10, "bold"),
            text_color=("#64748B", "#9CA3AF"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

        #metric value changes when the preview is refreshed.
        value_label = ctk.CTkLabel(
            metric,
            text="-",
            font=("Segoe UI", 18, "bold"),
            text_color=("#1D4ED8", "#93C5FD"),
            anchor="w",
        )
        value_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
        self.preview_metric_labels[key] = value_label

    def _browse(self, file_type: FileReaderType, mode: UploadMode) -> None:
        #open the system file picker and let the user select a local text file.
        filepath = filedialog.askopenfilename(
            title=f"Choose input file to {mode.value}",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )

        #if the user cancels the file picker, keep the current screen state.
        if not filepath:
            return

        #delegate validation and parsing to the service, then show the result.
        result = self.upload_service.upload(file_type, filepath, mode)
        self._display_result(result)

    def _handle_theme_toggle(self) -> None:
        """Switch between light and dark mode."""
        handle_theme_toggle(
            self._on_theme_toggle,
            self._theme_button,
            self._theme_button_text,
        )

    def _display_result(self, result: UploadResult) -> None:
        #update only the row that belongs to the uploaded file type.
        label = self.status_labels[result.file_type]

        if result.success:
            #store the path for future screens and show a green success message.
            self.selected_paths[result.file_type] = result.path
            label.configure(
                text=(
                    f"{result.mode.display_name}: {result.path.name} - "
                    f"{result.item_count} item(s), {result.cached_count} total"
                ),
                text_color="#147A39",
            )
        else:
            #invalid files stay visible as red feedback so the user knows what to fixe before continuing.
            label.configure(text=result.message, text_color="#B00020")

        # Refresh the global readiness message and parsed-data preview after very upload attempt.
        # Failed uploads leave the previous preview intact because FileUploadService preserves valid cached state.
        self._refresh_ready_label()
        self._refresh_preview()

    def _export(self, file_type: FileReaderType) -> None:
        """Choose a destination path and export the requested uploaded dataset."""
        filepath = filedialog.asksaveasfilename(
            title="Export uploaded dataset",
            defaultextension=".txt",
            initialfile=self._default_export_filename(file_type),
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )

        if not filepath:
            return

        result = self.export_service.export(file_type, filepath)
        self._display_export_result(result)

    def _display_export_result(self, result: ExportResult) -> None:
        """Show export success or failure feedback in the upload screen."""
        if result.success:
            self.export_status_label.configure(
                text=(
                    f"Exported {result.item_count} item(s) to "
                    f"{result.path.name}."
                ),
                text_color="#147A39",
            )
        else:
            self.export_status_label.configure(
                text=result.message,
                text_color="#B00020",
            )

    def _refresh_ready_label(self) -> None:
        """Refresh the global upload-readiness message."""
        ready = self.upload_service.is_ready_for_scheduling()

        if ready:
            self.ready_label.configure(
                text="All files loaded successfully.",
                text_color="#147A39",
            )
        else:
            self.ready_label.configure(
                text="Load all required files to continue.",
                text_color="#666666",
            )

        continue_button = getattr(self, "_continue_button", None)
        if continue_button is not None:
            continue_button.configure(
                state="normal" if ready else "disabled"
            )

    def _handle_next(self) -> None:
        """Move to the next workflow step when all required inputs are loaded."""
        if not self.upload_service.is_ready_for_scheduling():
            self.ready_label.configure(
                text="Load all required files to continue.",
                text_color="#B00020",
            )
            return

        if self._on_next is not None:
            self._on_next()

    def _refresh_upload_row_statuses(self) -> None:
        """Mirror already cached data in the three upload status rows."""
        uploaded_data = self.upload_service.get_uploaded_data()
        cached_counts = {
            FileReaderType.COURSES: len(uploaded_data.courses or []),
            FileReaderType.PROGRAMS: len(uploaded_data.programs or []),
            FileReaderType.EXAM_PERIODS: len(uploaded_data.exam_periods or []),
        }

        for file_type, count in cached_counts.items():
            label = self.status_labels.get(file_type)
            if label is None:
                continue

            if count:
                label.configure(
                    text=f"Loaded from saved data - {count} item(s)",
                    text_color="#147A39",
                )
            else:
                label.configure(
                    text="No file loaded",
                    text_color=("#5F6368", "#A8A8A8"),
                )

    def _refresh_preview(self) -> None:
        """Reload parsed upload data and redraw the preview text."""
        snapshot = self.data_presenter.refresh()
        preview = self._format_snapshot(snapshot)

        if hasattr(self, "preview_metric_labels"):
            self._refresh_preview_metrics(snapshot)

        self.preview_textbox.configure(state="normal")
        self.preview_textbox.delete("1.0", "end")
        self.preview_textbox.insert("end", preview)
        self.preview_textbox.configure(state="disabled")

    def _refresh_preview_metrics(self, snapshot: UploadedDataSnapshot) -> None:
        """Refresh the visual summary cards above the raw preview details."""
        #read the summary numbers from the presenter snapshot.
        metadata = snapshot.metadata

        #convert the metadata values to text for the GUI labels.
        values = {
            "courses": str(metadata.course_count),
            "programs": str(metadata.program_count),
            "periods": str(metadata.exam_period_count),
            "ready": "Ready" if metadata.is_complete else "Missing",
        }

        #update each metric label if it exists.
        for key, value in values.items():
            label = self.preview_metric_labels.get(key)
            if label is not None:
                label.configure(text=value)

        #the ready metric is green when the data is complete and red otherwise.
        ready_label = self.preview_metric_labels.get("ready")
        if ready_label is not None:
            ready_label.configure(
                text_color="#147A39" if metadata.is_complete else "#B00020"
            )

    @staticmethod
    def _default_export_filename(file_type: FileReaderType) -> str:
        """Return the suggested file name for each export action."""
        names = {
            FileReaderType.COURSES: "SchedulixCoursesExport.txt",
            FileReaderType.PROGRAMS: "SchedulixProgramsExport.txt",
            FileReaderType.EXAM_PERIODS: "SchedulixExamPeriodsExport.txt",
        }
        return names.get(file_type, "SchedulixExport.txt")

    @staticmethod
    def _format_snapshot(snapshot: UploadedDataSnapshot) -> str:
        """Convert the display snapshot into a readable preview report."""
        #metadata contains the totals shown at the top of the preview.
        metadata = snapshot.metadata
        readiness = "Ready for scheduling" if metadata.is_complete else "Missing data"

        #start the preview with a short overview section.
        lines: list[str] = [
            "Overview",
            f"Courses: {metadata.course_count} loaded, "
            f"{metadata.exam_course_count} exam course(s)",
            f"Programs: {metadata.program_count} selected",
            f"Exam periods: {metadata.exam_period_count} loaded, "
            f"{metadata.total_excluded_date_count} excluded date(s)",
            f"Enrollment links: {metadata.total_enrollment_count}",
            f"Status: {readiness}",
        ]

        # add evaluation type counts only when they exist.
        if metadata.evaluation_counts:
            evaluation_summary = ", ".join(
                f"{name}: {count}"
                for name, count in sorted(metadata.evaluation_counts.items())
            )
            lines.append(f"Evaluation types: {evaluation_summary}")

        # add course rows to the preview.
        lines.extend(["", "Courses"])
        if not snapshot.courses:
            lines.append("No courses loaded.")
        else:
            for course in snapshot.courses:
                # join all program numbers for this course.
                programs = ", ".join(course.program_numbers) or "No programs"
                lines.append(
                    f"{course.course_number} - {course.name}\n"
                    f"  Instructor: {course.instructor}\n"
                    f"  Evaluation: {course.evaluation_type}\n"
                    f"  Enrollments: {course.enrollment_count}\n"
                    f"  Programs: {programs}"
                )

        # add selected program rows to the preview.
        lines.extend(["", "Programs"])
        if not snapshot.programs:
            lines.append("No programs loaded.")
        else:
            for program in snapshot.programs:
                lines.append(program)

        # add exam period rows to the preview.
        lines.extend(["", "Exam Periods"])
        if not snapshot.exam_periods:
            lines.append("No exam periods loaded.")
        else:
            for exam_period in snapshot.exam_periods:
                lines.append(
                    f"{exam_period.semester} {exam_period.moed}\n"
                    f"  Dates: {exam_period.start_date} to {exam_period.end_date}\n"
                    f"  Duration: {exam_period.day_count} day(s)\n"
                    f"  Excluded dates: {exam_period.excluded_count}"
                )

        return "\n".join(lines)
