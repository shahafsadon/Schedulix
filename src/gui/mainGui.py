"""Backward-compatible GUI entry point for older imports and tests."""

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise SystemExit(
        "Missing dependency: customtkinter. "
        "Install project dependencies with: "
        ".venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.cache_manager import CacheManager
from gui.fileUploadScreen import FileUploadScreen
from gui.services.uploadService import FileUploadService
from gui.services.uploadedDataExportService import UploadedDataExportService
from gui.presenters.uploadedDataPresenter import UploadedDataPresenter


def main() -> None:
    """Run the legacy-compatible Version 2.0 upload entry screen."""
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Schedulix - File Upload")
    root.geometry("980x680")

    cache = CacheManager()
    upload_service = FileUploadService(cache_manager=cache)
    uploaded_data = upload_service.get_uploaded_data()
    data_presenter = UploadedDataPresenter(
        cache_manager=cache,
        uploaded_data=uploaded_data,
    )
    export_service = UploadedDataExportService(
        cache_manager=cache,
        uploaded_data=uploaded_data,
    )

    screen = FileUploadScreen(
        root,
        upload_service=upload_service,
        data_presenter=data_presenter,
        export_service=export_service,
    )
    screen.pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
