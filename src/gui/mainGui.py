import tkinter as tk

from gui.fileUploadScreen import FileUploadScreen


def main() -> None:
    """Run the Schedulix Version 2.0 GUI upload workflow."""
    # Create the root desktop window for the Version 2.0 GUI.
    root = tk.Tk()
    root.title("Schedulix - File Upload")
    root.geometry("760x320")

    # Show the first workflow screen: loading and validating input files.
    screen = FileUploadScreen(root)
    screen.pack(fill="both", expand=True)

    # Start Tkinter's event loop so button clicks and file dialogs work.
    root.mainloop()


if __name__ == "__main__":
    main()
