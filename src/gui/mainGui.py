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
from gui.screens.themeToggle import theme_button_text_for_mode


def main() -> None:
    """Run the legacy-compatible Version 2.0 upload entry screen."""
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    theme_mode = {"value": "Light"}

    def theme_button_text() -> str:
        """Return the next theme action for the upload screen."""
        return theme_button_text_for_mode(theme_mode["value"])

    def toggle_theme() -> str:
        """Switch the upload screen between light and dark mode."""
        theme_mode["value"] = "Light" if theme_mode["value"] == "Dark" else "Dark"
        ctk.set_appearance_mode(theme_mode["value"])
        return theme_mode["value"]

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
        on_theme_toggle=toggle_theme,
        theme_button_text=theme_button_text,
    )
    screen.pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
