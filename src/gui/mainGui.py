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
from gui.uploadService import FileUploadService
from gui.uploadedDataExportService import UploadedDataExportService
from gui.uploadedDataPresenter import UploadedDataPresenter


def main() -> None:
    """Run the Schedulix Version 2.0 GUI upload workflow."""
    # Use customTkinter as defined in the Version 2.0 software design document.
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    # Create the root desktop window for the Version 2.0 GUI.
    root = ctk.CTk()
    root.title("Schedulix - File Upload")
    root.geometry("980x680")

    # One shared cache instance is injected into the upload service so file
    # replacements/appends update the same state later wizard screens consume.
    cache = CacheManager()
    upload_service = FileUploadService(cache_manager=cache)
    data_presenter = UploadedDataPresenter(
        cache_manager=cache,
        uploaded_data=upload_service.get_uploaded_data(),
    )
    export_service = UploadedDataExportService(
        cache_manager=cache,
        uploaded_data=upload_service.get_uploaded_data(),
    )

    # Show the first workflow screen: loading and validating input files.
    screen = FileUploadScreen(
        root,
        upload_service=upload_service,
        data_presenter=data_presenter,
        export_service=export_service,
    )
    screen.pack(fill="both", expand=True)

    # Start Tkinter's event loop so button clicks and file dialogs work.
    root.mainloop()


if __name__ == "__main__":
    main()
