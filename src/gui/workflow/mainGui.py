try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise SystemExit(
        "Missing dependency: customtkinter. "
        "Install project dependencies with: "
        ".venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from gui.workflow.workflowApp import SchedulixWorkflow


def main() -> None:
    """Run the Schedulix Version 2.0 GUI upload workflow."""
    # Use customTkinter as defined in the Version 2.0 software design document.
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    # Create the root desktop window for the Version 2.0 GUI.
    root = ctk.CTk()
    root.title("Schedulix - File Upload")
    root.geometry("980x680")

    # Show the full Version 2.0 workflow shell.
    workflow = SchedulixWorkflow(root)
    workflow.pack(fill="both", expand=True)

    # Start Tkinter's event loop so button clicks and file dialogs work.
    root.mainloop()


if __name__ == "__main__":
    main()
