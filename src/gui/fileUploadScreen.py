from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from fileReader.baseFileReader import FileReaderType
from gui.uploadService import FileUploadService, UploadResult


class FileUploadScreen(ttk.Frame):
    """
    File upload screen for the Version 2.0 GUI workflow.

    The screen lets the user choose the three required input files, validates
    them through the existing readers, and displays upload feedback.
    """

    def __init__(
        self,
        master: tk.Misc,
        upload_service: FileUploadService | None = None,
    ) -> None:
        super().__init__(master, padding=16)
        # The screen talks to this service instead of calling file readers
        # directly. This keeps GUI code focused on display and user actions.
        self.upload_service = upload_service or FileUploadService()

        # Keep labels and selected paths by file type so each upload row can be
        # updated independently after the user chooses a file.
        self.status_labels: dict[FileReaderType, ttk.Label] = {}
        self.selected_paths: dict[FileReaderType, Path] = {}

        self._build()

    def _build(self) -> None:
        # Let the status column expand when the window is resized.
        self.columnconfigure(1, weight=1)

        title = ttk.Label(
            self,
            text="Load Input Files",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        rows = [
            (FileReaderType.COURSES, "Courses file"),
            (FileReaderType.PROGRAMS, "Programs file"),
            (FileReaderType.EXAM_PERIODS, "Exam periods file"),
        ]

        # Build one upload row for every required Version 2.0 input file.
        for row_index, (file_type, label_text) in enumerate(rows, start=1):
            ttk.Label(self, text=label_text).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=6,
            )

            status = ttk.Label(self, text="No file loaded", foreground="#666666")
            status.grid(row=row_index, column=1, sticky="ew", pady=6)
            self.status_labels[file_type] = status

            ttk.Button(
                self,
                text="Browse",
                # Bind the current file type so every button uploads to the
                # correct reader instead of all buttons using the last row.
                command=lambda current_type=file_type: self._browse(current_type),
            ).grid(row=row_index, column=2, sticky="e", pady=6)

        # This label summarizes whether all required files are ready.
        self.ready_label = ttk.Label(
            self,
            text="Load all required files to continue.",
            foreground="#666666",
        )
        self.ready_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def _browse(self, file_type: FileReaderType) -> None:
        # Open the system file picker and let the user select a local text file.
        filepath = filedialog.askopenfilename(
            title="Choose input file",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )

        # If the user cancels the file picker, keep the current screen state.
        if not filepath:
            return

        # Delegate validation and parsing to the service, then show the result.
        result = self.upload_service.upload(file_type, filepath)
        self._display_result(result)

    def _display_result(self, result: UploadResult) -> None:
        # Update only the row that belongs to the uploaded file type.
        label = self.status_labels[result.file_type]

        if result.success:
            # Store the path for future screens and show a green success message.
            self.selected_paths[result.file_type] = result.path
            label.configure(
                text=f"{result.path.name} - {result.item_count} item(s)",
                foreground="#147A39",
            )
        else:
            # Invalid files stay visible as red feedback so the user knows what
            # needs to be fixed before continuing.
            label.configure(text=result.message, foreground="#B00020")

        # Refresh the global readiness message after every upload attempt.
        if self.upload_service.is_ready_for_scheduling():
            self.ready_label.configure(
                text="All files loaded successfully.",
                foreground="#147A39",
            )
        else:
            self.ready_label.configure(
                text="Load all required files to continue.",
                foreground="#666666",
            )
