"""Integration tests for the Version 2.0 GUI workflows (SCRUM-107).

The real GUI uses the passive MVP pattern: screens delegate state changes to
services and presenters. These tests keep the customTkinter window closed and
exercise the same boundaries headlessly, which makes them safe for CI while
still validating the UI-to-backend hand-offs.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch
from gui.uploadedDataPresenter import UploadedDataSnapshot, UploadedDataMetadata

from application.cache_manager import CacheManager
from fileReader.baseFileReader import FileReaderType
from gui.programDetailsPresenter import ProgramDetailsPresenter
from gui.programSelectionPresenter import ProgramSelectionPresenter
from gui.schedulingPresenter import SchedulingPresenter
from gui.uploadService import FileUploadService
from output.outputWriter import OutputWriter


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "data" / "examples"
COURSES_PATH = EXAMPLES / "CourseExample.txt"
PROGRAMS_PATH = EXAMPLES / "ProgramsExample.txt"
PERIODS_PATH = EXAMPLES / "DatesExample.txt"


class _FakeLabel:
    """Minimal CTkLabel stand-in that records the latest configure values."""

    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)


def _load_headless_screen_classes():
    """Import screen classes without installing or opening customTkinter."""
    fake_ctk = ModuleType("customtkinter")
    fake_ctk.CTkFrame = type("CTkFrame", (), {})

    with patch.dict(sys.modules, {"customtkinter": fake_ctk}):
        upload_module = importlib.import_module("gui.fileUploadScreen")
        config_module = importlib.import_module("gui.programConfigScreen")

    return upload_module.FileUploadScreen, config_module.ProgramConfigScreen


def _upload_examples() -> FileUploadService:
    """Load the three repository example files through the real upload service."""
    service = FileUploadService()

    assert service.upload_courses(COURSES_PATH).success
    assert service.upload_programs(PROGRAMS_PATH).success
    assert service.upload_exam_periods(PERIODS_PATH).success
    assert service.is_ready_for_scheduling()

    return service


def _new_cache(tmp_path: Path, monkeypatch) -> CacheManager:
    """Create an isolated write-through cache for one workflow test."""
    monkeypatch.setattr(
        CacheManager,
        "_PKL_PATH",
        tmp_path / "internal_data.pkl",
    )
    return CacheManager()


def _store_uploaded_data(
    cache: CacheManager,
    service: FileUploadService,
) -> None:
    """Perform the wizard-shell hand-off from uploads into the shared cache."""
    uploaded = service.get_uploaded_data()

    assert uploaded.courses is not None
    assert uploaded.exam_periods is not None

    cache.set_courses(uploaded.courses)
    cache.set_exam_periods(uploaded.exam_periods)


def _select_programs_and_generate(cache: CacheManager) -> int:
    """Select one real program and trigger the real scheduling pipeline."""
    selection = ProgramSelectionPresenter(cache.get_courses())
    result = selection.toggle("83101")

    assert result.accepted
    assert selection.can_proceed()

    cache.set_selected_programs(selection.selected_programs)
    generation = SchedulingPresenter(cache).generate()

    assert generation.success
    assert generation.schedule_count > 0
    assert len(cache.get_generated_schedules()) == generation.schedule_count

    return generation.schedule_count


def test_upload_screen_feedback_becomes_ready_only_after_all_files_are_loaded(
) -> None:
    """The upload screen must mirror the real service readiness state."""
    FileUploadScreen, _ = _load_headless_screen_classes()

    screen = object.__new__(FileUploadScreen)
    screen.upload_service = FileUploadService()
    screen.selected_paths = {}
    # data_presenter and preview_textbox were added in SCRUM-119; stub them so
    # _display_result can call _refresh_preview without a real Tk display.
    screen.data_presenter = MagicMock()
    _empty_meta = UploadedDataMetadata(0, 0, 0, 0, 0, 0, {}, False)
    screen.data_presenter.refresh.return_value = UploadedDataSnapshot([], [], [], _empty_meta)
    screen.preview_textbox = MagicMock()
    screen.status_labels = {
        FileReaderType.COURSES: _FakeLabel(),
        FileReaderType.PROGRAMS: _FakeLabel(),
        FileReaderType.EXAM_PERIODS: _FakeLabel(),
    }
    screen.ready_label = _FakeLabel()

    courses = screen.upload_service.upload_courses(COURSES_PATH)
    screen._display_result(courses)

    assert (
        screen.ready_label.options["text"]
        == "Load all required files to continue."
    )

    programs = screen.upload_service.upload_programs(PROGRAMS_PATH)
    screen._display_result(programs)

    assert (
        screen.ready_label.options["text"]
        == "Load all required files to continue."
    )

    periods = screen.upload_service.upload_exam_periods(PERIODS_PATH)
    screen._display_result(periods)

    assert screen.upload_service.is_ready_for_scheduling()
    assert screen.ready_label.options == {
        "text": "All files loaded successfully.",
        "text_color": "#147A39",
    }
    assert screen.selected_paths == {
        FileReaderType.COURSES: COURSES_PATH,
        FileReaderType.PROGRAMS: PROGRAMS_PATH,
        FileReaderType.EXAM_PERIODS: PERIODS_PATH,
    }


def test_failed_reupload_keeps_the_last_valid_uploaded_courses(
    tmp_path: Path,
) -> None:
    """A bad replacement file must not destroy the previous valid upload."""
    service = FileUploadService()
    valid_result = service.upload_courses(COURSES_PATH)
    original_courses = service.get_uploaded_data().courses

    invalid_path = tmp_path / "invalid_courses.txt"
    invalid_path.write_text(
        """$$$$
Broken Course
8319A
Dr. Test
83101,1,FALL,Obligatory
Exam
""",
        encoding="utf-8",
    )

    failed_result = service.upload_courses(invalid_path)

    assert valid_result.success
    assert not failed_result.success
    assert "upload failed" in failed_result.message
    assert service.get_uploaded_data().courses is original_courses


def test_program_navigation_blocks_next_until_the_selection_is_valid(
) -> None:
    """The program-config screen must not navigate forward with zero programs."""
    _, ProgramConfigScreen = _load_headless_screen_classes()

    selection = ProgramSelectionPresenter(
        _upload_examples().get_uploaded_data().courses or []
    )
    visited_steps: list[str] = []

    screen = object.__new__(ProgramConfigScreen)
    screen.selection_presenter = selection
    screen._status_label = _FakeLabel()
    screen._on_next = lambda: visited_steps.append("generation")

    screen._handle_next()

    assert visited_steps == []
    assert (
        screen._status_label.options["text"]
        == "Select at least one program to continue."
    )

    assert selection.toggle("83101").accepted
    screen._handle_next()

    assert visited_steps == ["generation"]


def test_generation_workflow_connects_upload_selection_cache_and_scheduler(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Uploaded data and a UI selection must feed the real scheduling backend."""
    service = _upload_examples()
    cache = _new_cache(tmp_path, monkeypatch)
    _store_uploaded_data(cache, service)

    details = ProgramDetailsPresenter(
        cache.get_courses()
    ).get_details("83101")

    schedule_count = _select_programs_and_generate(cache)

    assert details.program_number == "83101"
    assert details.course_count > 0
    assert details.groups
    assert schedule_count == len(cache.get_generated_schedules())


def test_export_workflow_writes_the_generated_cache_to_a_readable_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Generated systems stored by the GUI backend must be exportable as text."""
    service = _upload_examples()
    cache = _new_cache(tmp_path, monkeypatch)
    _store_uploaded_data(cache, service)

    schedule_count = _select_programs_and_generate(cache)

    output_path = tmp_path / "exports" / "exam_schedules.txt"

    created_path = OutputWriter().write(
        cache.get_generated_schedules(),
        output_path,
    )
    output = created_path.read_text(encoding="utf-8")

    assert created_path == output_path
    assert output_path.exists()
    assert "Schedulix Exam Schedules" in output
    assert "Schedule 1" in output
    assert "Physics 1" in output
    assert "Calculus 1" in output
    assert "Software Project" not in output
    assert output.count("Schedule ") == schedule_count


def test_complete_headless_wizard_flow_reaches_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Run the complete Version 2.0 workflow from uploads to exported schedules."""
    stages = ["upload"]
    service = _upload_examples()

    cache = _new_cache(tmp_path, monkeypatch)
    _store_uploaded_data(cache, service)
    stages.append("program-selection")

    schedule_count = _select_programs_and_generate(cache)
    stages.append("generation")

    output_path = tmp_path / "wizard" / "exam_schedules.txt"

    OutputWriter().write(
        cache.get_generated_schedules(),
        output_path,
    )
    stages.append("export")

    assert stages == [
        "upload",
        "program-selection",
        "generation",
        "export",
    ]
    assert schedule_count > 0
    assert output_path.exists()
    assert output_path.stat().st_size > 0