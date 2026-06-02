from pathlib import Path
from tkinter import filedialog

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from fileReader.baseFileReader import FileReaderType
from gui.uploadService import FileUploadService, UploadMode, UploadResult
from gui.uploadedDataPresenter import UploadedDataPresenter, UploadedDataSnapshot


class FileUploadScreen(ctk.CTkFrame):
    """
    File upload screen for the Version 2.0 GUI workflow.

    The screen lets the user choose the three required input files, either
    replace or append each dataset, validates files through the existing
    readers, and displays upload feedback.
    """

    def __init__(
        self,
        master,
        upload_service: FileUploadService | None = None,
        data_presenter: UploadedDataPresenter | None = None,
    ) -> None:
        super().__init__(master, corner_radius=0)
        # The screen talks to this service instead of calling file readers
        # directly. This keeps GUI code focused on display and user actions.
        self.upload_service = upload_service or FileUploadService()
        self.data_presenter = data_presenter or UploadedDataPresenter(
            cache_manager=self.upload_service.cache_manager,
            uploaded_data=self.upload_service.get_uploaded_data(),
        )

        # Keep labels and selected paths by file type so each upload row can be
        # updated independently after the user chooses a file.
        self.status_labels: dict[FileReaderType, ctk.CTkLabel] = {}
        self.selected_paths: dict[FileReaderType, Path] = {}

        self._build()

    def _build(self) -> None:
        # Let the status/preview columns expand when the window is resized.
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(6, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Load Input Files",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(16, 12))

        rows = [
            (FileReaderType.COURSES, "Courses file"),
            (FileReaderType.PROGRAMS, "Programs file"),
            (FileReaderType.EXAM_PERIODS, "Exam periods file"),
        ]

        # Build one upload row for every required Version 2.0 input file.
        for row_index, (file_type, label_text) in enumerate(rows, start=1):
            ctk.CTkLabel(self, text=label_text).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(16, 12),
                pady=6,
            )

            status = ctk.CTkLabel(
                self,
                text="No file loaded",
                text_color="#666666",
            )
            status.grid(row=row_index, column=1, sticky="ew", pady=6)
            self.status_labels[file_type] = status

            ctk.CTkButton(
                self,
                text="Replace",
                # Bind the current file type so every button uploads to the
                # correct reader instead of all buttons using the last row.
                command=lambda current_type=file_type: self._browse(
                    current_type,
                    UploadMode.REPLACE,
                ),
            ).grid(row=row_index, column=2, sticky="e", padx=(12, 16), pady=6)

            ctk.CTkButton(
                self,
                text="Append",
                fg_color="transparent",
                border_width=1,
                command=lambda current_type=file_type: self._browse(
                    current_type,
                    UploadMode.APPEND,
                ),
            ).grid(row=row_index, column=3, sticky="e", padx=(0, 16), pady=6)

        # This label summarizes whether all required files are ready.
        self.ready_label = ctk.CTkLabel(
            self,
            text="Load all required files to continue.",
            text_color="#666666",
        )
        self.ready_label.grid(
            row=4,
            column=0,
            columnspan=4,
            sticky="w",
            padx=16,
            pady=(16, 8),
        )

        self._build_preview()
        self._refresh_ready_label()
        self._refresh_preview()

    def _build_preview(self) -> None:
        """Build the parsed-data preview area and refresh action."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=5, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Uploaded Data Preview",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header,
            text="Refresh",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self._refresh_preview,
        ).grid(row=0, column=1, sticky="e")

        self.preview_textbox = ctk.CTkTextbox(
            self,
            height=280,
            font=("Consolas", 11),
            wrap="word",
        )
        self.preview_textbox.grid(
            row=6,
            column=0,
            columnspan=4,
            sticky="nsew",
            padx=16,
            pady=(0, 16),
        )

    def _browse(self, file_type: FileReaderType, mode: UploadMode) -> None:
        # Open the system file picker and let the user select a local text file.
        filepath = filedialog.askopenfilename(
            title=f"Choose input file to {mode.value}",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )

        # If the user cancels the file picker, keep the current screen state.
        if not filepath:
            return

        # Delegate validation and parsing to the service, then show the result.
        result = self.upload_service.upload(file_type, filepath, mode)
        self._display_result(result)

    def _display_result(self, result: UploadResult) -> None:
        # Update only the row that belongs to the uploaded file type.
        label = self.status_labels[result.file_type]

        if result.success:
            # Store the path for future screens and show a green success message.
            self.selected_paths[result.file_type] = result.path
            label.configure(
                text=(
                    f"{result.mode.display_name}: {result.path.name} - "
                    f"{result.item_count} item(s), {result.cached_count} total"
                ),
                text_color="#147A39",
            )
        else:
            # Invalid files stay visible as red feedback so the user knows what
            # needs to be fixed before continuing.
            label.configure(text=result.message, text_color="#B00020")

        # Refresh the global readiness message and parsed-data preview after
        # every upload attempt. Failed uploads leave the previous preview intact
        # because FileUploadService preserves valid cached state.
        self._refresh_ready_label()
        self._refresh_preview()

    def _refresh_ready_label(self) -> None:
        """Refresh the global upload-readiness message."""
        if self.upload_service.is_ready_for_scheduling():
            self.ready_label.configure(
                text="All files loaded successfully.",
                text_color="#147A39",
            )
        else:
            self.ready_label.configure(
                text="Load all required files to continue.",
                text_color="#666666",
            )

    def _refresh_preview(self) -> None:
        """Reload parsed upload data and redraw the preview text."""
        snapshot = self.data_presenter.refresh()
        preview = self._format_snapshot(snapshot)

        self.preview_textbox.configure(state="normal")
        self.preview_textbox.delete("1.0", "end")
        self.preview_textbox.insert("end", preview)
        self.preview_textbox.configure(state="disabled")

    @staticmethod
    def _format_snapshot(snapshot: UploadedDataSnapshot) -> str:
        """Convert the display snapshot into compact multiline preview text."""
        metadata = snapshot.metadata
        lines: list[str] = [
            "Metadata",
            f"- Courses loaded: {metadata.course_count}",
            f"- Selected programs loaded: {metadata.program_count}",
            f"- Exam periods loaded: {metadata.exam_period_count}",
            f"- Exam courses: {metadata.exam_course_count}",
            f"- Program enrollments: {metadata.total_enrollment_count}",
            f"- Excluded exam dates: {metadata.total_excluded_date_count}",
            f"- Ready for scheduling: {'Yes' if metadata.is_complete else 'No'}",
        ]

        if metadata.evaluation_counts:
            evaluation_summary = ", ".join(
                f"{name}: {count}"
                for name, count in sorted(metadata.evaluation_counts.items())
            )
            lines.append(f"- Evaluation types: {evaluation_summary}")

        lines.extend(["", "Courses"])
        if not snapshot.courses:
            lines.append("- No courses loaded.")
        else:
            for course in snapshot.courses:
                programs = ", ".join(course.program_numbers) or "No programs"
                lines.append(
                    f"- {course.course_number} | {course.name} | "
                    f"{course.instructor} | {course.evaluation_type} | "
                    f"{course.enrollment_count} enrollment(s) | {programs}"
                )

        lines.extend(["", "Programs"])
        if not snapshot.programs:
            lines.append("- No programs loaded.")
        else:
            for program in snapshot.programs:
                lines.append(f"- {program}")

        lines.extend(["", "Exam Periods"])
        if not snapshot.exam_periods:
            lines.append("- No exam periods loaded.")
        else:
            for exam_period in snapshot.exam_periods:
                lines.append(
                    f"- {exam_period.semester} {exam_period.moed} | "
                    f"{exam_period.start_date} to {exam_period.end_date} | "
                    f"{exam_period.day_count} day(s) | "
                    f"{exam_period.excluded_count} excluded"
                )

        return "\n".join(lines)
