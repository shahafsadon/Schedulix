from pathlib import Path
from unittest.mock import MagicMock

from fileReader.baseFileReader import FileReaderType
from gui.uploadService import UploadMode, UploadResult
from gui.uploadedDataExportService import ExportResult
from gui.uploadedDataPresenter import UploadedDataMetadata, UploadedDataSnapshot

from .gui_test_support import FakeLabel, load_screen_module


def _snapshot(*, complete: bool = False) -> UploadedDataSnapshot:
    metadata = UploadedDataMetadata(
        course_count=3,
        program_count=2,
        exam_period_count=1,
        exam_course_count=2,
        total_enrollment_count=4,
        total_excluded_date_count=1,
        evaluation_counts={"Exam": 2, "Project": 1},
        is_complete=complete,
    )

    return UploadedDataSnapshot([], [], [], metadata)


def _screen(module):
    screen = object.__new__(module.FileUploadScreen)
    screen.upload_service = MagicMock()
    screen.data_presenter = MagicMock()
    screen.export_service = MagicMock()
    screen.selected_paths = {}

    screen.status_labels = {
        FileReaderType.COURSES: FakeLabel(),
        FileReaderType.PROGRAMS: FakeLabel(),
        FileReaderType.EXAM_PERIODS: FakeLabel(),
    }

    screen.ready_label = FakeLabel()
    screen.export_status_label = FakeLabel()
    screen.preview_textbox = MagicMock()

    screen.preview_metric_labels = {
        "courses": FakeLabel(),
        "programs": FakeLabel(),
        "periods": FakeLabel(),
        "ready": FakeLabel(),
    }

    screen.data_presenter.refresh.return_value = _snapshot()

    return screen


def test_browse_cancel_does_not_upload(monkeypatch) -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    monkeypatch.setattr(
        module.filedialog,
        "askopenfilename",
        lambda **_kwargs: "",
    )

    screen._browse(FileReaderType.COURSES, UploadMode.REPLACE)

    screen.upload_service.upload.assert_not_called()


def test_browse_forwards_selected_path_type_and_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    source = tmp_path / "courses.txt"

    result = UploadResult(
        file_type=FileReaderType.COURSES,
        path=source,
        success=True,
        message="ok",
        mode=UploadMode.APPEND,
        item_count=2,
        cached_count=5,
    )

    screen.upload_service.upload.return_value = result
    screen._display_result = MagicMock()

    monkeypatch.setattr(
        module.filedialog,
        "askopenfilename",
        lambda **_kwargs: str(source),
    )

    screen._browse(FileReaderType.COURSES, UploadMode.APPEND)

    screen.upload_service.upload.assert_called_once_with(
        FileReaderType.COURSES,
        str(source),
        UploadMode.APPEND,
    )

    screen._display_result.assert_called_once_with(result)


def test_successful_upload_feedback_stores_path_and_refreshes_preview(
    tmp_path: Path,
) -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    screen.upload_service.is_ready_for_scheduling.return_value = True

    path = tmp_path / "programs.txt"

    screen._display_result(
        UploadResult(
            file_type=FileReaderType.PROGRAMS,
            path=path,
            success=True,
            message="ok",
            mode=UploadMode.REPLACE,
            item_count=3,
            cached_count=3,
        )
    )

    assert screen.selected_paths[FileReaderType.PROGRAMS] == path

    assert screen.status_labels[FileReaderType.PROGRAMS].options == {
        "text": "Replace: programs.txt - 3 item(s), 3 total",
        "text_color": "#147A39",
    }

    assert screen.ready_label.options["text"] == (
        "All files loaded successfully."
    )

    screen.data_presenter.refresh.assert_called_once()


def test_export_cancel_does_not_call_service(monkeypatch) -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: "",
    )

    screen._export(FileReaderType.EXAM_PERIODS)

    screen.export_service.export.assert_not_called()


def test_export_forwards_destination_and_shows_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    output = tmp_path / "courses-export.txt"

    result = ExportResult(
        FileReaderType.COURSES,
        output,
        True,
        "done",
        7,
    )

    screen.export_service.export.return_value = result

    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(output),
    )

    screen._export(FileReaderType.COURSES)

    screen.export_service.export.assert_called_once_with(
        FileReaderType.COURSES,
        str(output),
    )

    assert screen.export_status_label.options == {
        "text": "Exported 7 item(s) to courses-export.txt.",
        "text_color": "#147A39",
    }


def test_export_failure_is_visible_in_red() -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    result = ExportResult(
        FileReaderType.PROGRAMS,
        Path("unused.txt"),
        False,
        "Nothing to export.",
    )

    screen._display_export_result(result)

    assert screen.export_status_label.options == {
        "text": "Nothing to export.",
        "text_color": "#B00020",
    }


def test_preview_metrics_mirror_snapshot_readiness() -> None:
    module, _ = load_screen_module("fileUploadScreen.py")
    screen = _screen(module)

    screen._refresh_preview_metrics(_snapshot(complete=True))

    assert screen.preview_metric_labels["courses"].options["text"] == "3"
    assert screen.preview_metric_labels["programs"].options["text"] == "2"
    assert screen.preview_metric_labels["periods"].options["text"] == "1"

    assert screen.preview_metric_labels["ready"].options == {
        "text": "Ready",
        "text_color": "#147A39",
    }


def test_constructor_builds_three_required_upload_rows_and_preview() -> None:
    module, fake_ctk = load_screen_module("fileUploadScreen.py")

    service = MagicMock()
    service.is_ready_for_scheduling.return_value = False
    service.get_uploaded_data.return_value = MagicMock()

    presenter = MagicMock()
    presenter.refresh.return_value = _snapshot()

    screen = module.FileUploadScreen(
        fake_ctk.CTkFrame(),
        upload_service=service,
        data_presenter=presenter,
        export_service=MagicMock(),
    )

    assert set(screen.status_labels) == {
        FileReaderType.COURSES,
        FileReaderType.PROGRAMS,
        FileReaderType.EXAM_PERIODS,
    }

    assert set(screen.preview_metric_labels) == {
        "courses",
        "programs",
        "periods",
        "ready",
    }

    assert screen.ready_label.options["text"] == (
        "Load all required files to continue."
    )


def test_format_snapshot_lists_loaded_rows() -> None:
    from gui.uploadedDataPresenter import CoursePreview, ExamPeriodPreview

    module, _ = load_screen_module("fileUploadScreen.py")

    snapshot = UploadedDataSnapshot(
        courses=[
            CoursePreview(
                course_number="12345",
                name="Algorithms",
                instructor="Dr. Ada",
                evaluation_type="Exam",
                enrollment_count=1,
                program_numbers=["83101"],
            )
        ],
        programs=["83101"],
        exam_periods=[
            ExamPeriodPreview(
                semester="FALL",
                moed="Aleph",
                start_date="01-01-2026",
                end_date="07-01-2026",
                day_count=7,
                excluded_count=1,
            )
        ],
        metadata=UploadedDataMetadata(
            1,
            1,
            1,
            1,
            1,
            1,
            {"Exam": 1},
            True,
        ),
    )

    report = module.FileUploadScreen._format_snapshot(snapshot)

    assert "12345 - Algorithms" in report
    assert "83101" in report
    assert "FALL Aleph" in report
    assert "Excluded dates: 1" in report