import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from .gui_test_support import FakeFrame, make_fake_ctk


def _load_main_gui(fake_ctk):
    project_root = Path(__file__).resolve().parents[3]
    source = project_root / "src" / "gui" / "mainGui.py"

    spec = importlib.util.spec_from_file_location(
        "_headless_main_gui",
        source,
    )

    module = importlib.util.module_from_spec(spec)

    with patch.dict(sys.modules, {"customtkinter": fake_ctk}):
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module


def test_main_configures_root_and_constructs_upload_workflow() -> None:
    fake_ctk = make_fake_ctk()

    root = FakeFrame()
    root.title = MagicMock()
    root.geometry = MagicMock()
    root.mainloop = MagicMock()

    fake_ctk.CTk = MagicMock(return_value=root)
    fake_ctk.set_appearance_mode = MagicMock()
    fake_ctk.set_default_color_theme = MagicMock()

    module = _load_main_gui(fake_ctk)

    module.CacheManager = MagicMock()
    module.FileUploadService = MagicMock()
    module.UploadedDataPresenter = MagicMock()
    module.UploadedDataExportService = MagicMock()

    screen = MagicMock()
    module.FileUploadScreen = MagicMock(return_value=screen)

    module.main()

    root.title.assert_called_once_with(
        "Schedulix - File Upload"
    )

    root.geometry.assert_called_once_with("980x680")

    module.FileUploadScreen.assert_called_once()

    screen.pack.assert_called_once_with(
        fill="both",
        expand=True,
    )

    root.mainloop.assert_called_once()