"""Headless responsiveness and usability checks for SCRUM-108.

The GUI follows passive MVP: views delegate work to services and presenters.
These tests exercise the observable UI behaviour without opening a desktop
window, so they remain stable in CI while still validating the real boundaries.
"""
from __future__ import annotations

import importlib
import sys
import threading
from datetime import date
from pathlib import Path
from time import monotonic, sleep
from types import ModuleType
from unittest.mock import MagicMock, patch
from gui.presenters.uploadedDataPresenter import UploadedDataSnapshot, UploadedDataMetadata

from application.async_runner import AsyncScheduleRunner, LoadingState
from fileReader.baseFileReader import FileReaderType
from gui.presenters.dateManagementPresenter import DateManagementPresenter
from gui.presenters.programSelectionPresenter import ProgramSelectionPresenter
from gui.services.uploadService import FileUploadService
from models import Course, ExamPeriod, ProgramEnrollment
from scheduling.examDateHandler import ExamDateHandler


class _FakeWidget:
    """Small stand-in for labels and buttons updated through configure()."""

    def __init__(self) -> None:
        self.options: dict[str, object] = {}
        self.history: list[dict[str, object]] = []

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)
        self.history.append(dict(kwargs))


class _FakeVariable:
    """Minimal BooleanVar replacement used to verify visual state rollback."""

    def __init__(self, value: bool = False) -> None:
        self.value = value

    def set(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value


class _FakeDetailsFrame:
    """Records expand/collapse operations without creating Tk widgets."""

    def __init__(self) -> None:
        self.children: list[object] = []
        self.grid_calls: list[dict[str, object]] = []
        self.grid_forget_count = 0

    def winfo_children(self) -> list[object]:
        return list(self.children)

    def grid(self, **kwargs) -> None:
        self.grid_calls.append(dict(kwargs))

    def grid_forget(self) -> None:
        self.grid_forget_count += 1


def _load_headless_screen_classes():
    """Import screen classes while replacing optional customTkinter in CI."""
    fake_ctk = ModuleType("customtkinter")
    fake_ctk.CTkFrame = type("CTkFrame", (), {})

    with patch.dict(sys.modules, {"customtkinter": fake_ctk}):
        upload_module = importlib.import_module("gui.screens.fileUploadScreen")
        config_module = importlib.import_module("gui.screens.programConfigScreen")

    return upload_module.FileUploadScreen, config_module.ProgramConfigScreen


def _period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
    )


def _course(program_number: str) -> Course:
    return Course(
        name=f"Course {program_number}",
        course_number=program_number,
        instructor="Dr. Test",
        programs=[
            ProgramEnrollment(
                program_number,
                1,
                "FALL",
                "Obligatory",
            )
        ],
        evaluation_type="Exam",
    )


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    """Poll a short-lived async state transition without race-prone sleeps."""
    deadline = monotonic() + timeout

    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.01)

    return predicate()


def test_loading_state_is_visible_while_background_work_is_active() -> None:
    """The view can show loading immediately and clear it after completion."""
    gate = threading.Event()
    started = threading.Event()
    completed = threading.Event()
    runner = AsyncScheduleRunner()

    accepted = runner.run(
        task=lambda: gate.wait(timeout=2),
        on_started=started.set,
        on_complete=lambda _result: completed.set(),
    )

    assert accepted
    assert started.is_set()
    assert runner.loading_state is LoadingState.RUNNING

    gate.set()

    assert completed.wait(timeout=2)
    assert _wait_until(lambda: runner.loading_state is LoadingState.IDLE)


def test_generation_returns_immediately_and_updates_cache_after_worker_finishes(
) -> None:
    """Schedule regeneration must not freeze the caller while work is running."""
    entered_generator = threading.Event()
    release_generator = threading.Event()
    completed = threading.Event()
    schedules = [object(), object()]

    class _BlockingGenerator:
        def generate_exam_systems(self, courses, exam_periods):
            entered_generator.set()
            release_generator.wait(timeout=2)
            return schedules

    cache = MagicMock()
    period = _period()

    presenter = DateManagementPresenter(
        exam_period=period,
        date_handler=ExamDateHandler(),
        cache_manager=cache,
        schedule_generator=_BlockingGenerator(),
        courses=[],
        exam_periods=[period],
    )

    runner = AsyncScheduleRunner()

    before = monotonic()

    accepted = presenter.on_regenerate_async(
        runner=runner,
        on_complete=lambda _result: completed.set(),
    )

    elapsed = monotonic() - before

    assert accepted
    assert elapsed < 0.5
    assert entered_generator.wait(timeout=1)
    assert runner.loading_state is LoadingState.RUNNING

    cache.set_generated_schedules.assert_not_called()

    release_generator.set()

    assert completed.wait(timeout=2)

    cache.set_generated_schedules.assert_called_once_with(schedules)
    assert _wait_until(lambda: runner.loading_state is LoadingState.IDLE)


def test_invalid_upload_shows_red_feedback_without_marking_screen_ready(
    tmp_path: Path,
) -> None:
    """Malformed user input must produce actionable feedback and preserve flow."""
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
        FileReaderType.COURSES: _FakeWidget(),
        FileReaderType.PROGRAMS: _FakeWidget(),
        FileReaderType.EXAM_PERIODS: _FakeWidget(),
    }

    screen.ready_label = _FakeWidget()

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

    result = screen.upload_service.upload_courses(invalid_path)
    screen._display_result(result)

    assert not result.success

    assert (
        "upload failed"
        in screen.status_labels[FileReaderType.COURSES].options["text"]
    )

    assert (
        screen.status_labels[FileReaderType.COURSES].options["text_color"]
        == "#B00020"
    )

    assert screen.ready_label.options == {
        "text": "Load all required files to continue.",
        "text_color": "#666666",
    }

    assert screen.selected_paths == {}


def test_reopening_program_details_reuses_existing_widgets() -> None:
    """Expand/collapse navigation must reuse the lazy-built details content."""
    _, ProgramConfigScreen = _load_headless_screen_classes()

    details = object()
    details_presenter = MagicMock()
    details_presenter.get_details.return_value = details

    frame = _FakeDetailsFrame()
    toggle = _FakeWidget()

    screen = object.__new__(ProgramConfigScreen)
    screen.details_presenter = details_presenter
    screen._expanded = {"83101": False}
    screen._detail_frames = {"83101": frame}
    screen._toggle_buttons = {"83101": toggle}

    def fill_details(target_frame, received_details) -> None:
        target_frame.children.append(received_details)

    screen._fill_details = fill_details

    screen._on_toggle("83101")  # first open: build lazily
    screen._on_toggle("83101")  # close: keep children
    screen._on_toggle("83101")  # reopen: reuse existing children

    details_presenter.get_details.assert_called_once_with("83101")

    assert frame.children == [details]
    assert len(frame.grid_calls) == 2
    assert frame.grid_forget_count == 1

    assert toggle.history == [
        {"text": "v"},
        {"text": ">"},
        {"text": "v"},
    ]


def test_rejected_selection_restores_checkbox_and_keeps_footer_consistent(
) -> None:
    """The visible checkbox state must stay aligned with presenter state."""
    _, ProgramConfigScreen = _load_headless_screen_classes()

    selection = ProgramSelectionPresenter(
        courses=[
            _course("83101"),
            _course("83102"),
        ],
        max_programs=1,
    )

    first_checkbox = _FakeVariable(value=True)
    second_checkbox = _FakeVariable(value=True)

    screen = object.__new__(ProgramConfigScreen)
    screen.selection_presenter = selection

    screen._checkbox_vars = {
        "83101": first_checkbox,
        "83102": second_checkbox,
    }

    screen._status_label = _FakeWidget()
    screen._next_button = _FakeWidget()

    screen._on_check("83101")

    assert selection.selected_programs == ["83101"]

    assert screen._status_label.options == {
        "text": "Selected: 1 / 1",
        "text_color": "#666666",
    }

    assert screen._next_button.options["state"] == "normal"

    screen._on_check("83102")

    assert selection.selected_programs == ["83101"]
    assert not second_checkbox.get()

    assert screen._status_label.options == {
        "text": "You can select at most 1 programs.",
        "text_color": "#B00020",
    }

    assert screen._next_button.options["state"] == "normal"
