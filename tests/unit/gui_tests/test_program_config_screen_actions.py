from unittest.mock import MagicMock

from gui.programDetailsPresenter import (
    CourseDetail,
    ProgramDetails,
    SemesterGroup,
)

from .gui_test_support import (
    FakeFrame,
    FakeLabel,
    load_screen_module,
    widgets_with_text,
)


def _selection(programs=()):
    selection = MagicMock()
    selection.available_programs = list(programs)
    selection.max_programs = 5
    selection.selection_count.return_value = 0
    selection.can_proceed.return_value = False
    selection.is_selected.return_value = False

    return selection


def test_constructor_shows_empty_state_when_no_programs_exist() -> None:
    module, fake_ctk = load_screen_module("programConfigScreen.py")

    module.ProgramConfigScreen(
        fake_ctk.CTkFrame(),
        _selection(),
        MagicMock(),
    )

    assert widgets_with_text(
        fake_ctk.CTkLabel,
        "No programs found. Load a courses file first.",
    )


def test_constructor_builds_selectable_program_rows() -> None:
    module, fake_ctk = load_screen_module("programConfigScreen.py")

    screen = module.ProgramConfigScreen(
        fake_ctk.CTkFrame(),
        _selection(["83101", "83102"]),
        MagicMock(),
    )

    assert set(screen._checkbox_vars) == {"83101", "83102"}
    assert set(screen._toggle_buttons) == {"83101", "83102"}
    assert set(screen._detail_frames) == {"83101", "83102"}


def test_next_is_blocked_until_at_least_one_program_is_selected() -> None:
    module, _ = load_screen_module("programConfigScreen.py")

    screen = object.__new__(module.ProgramConfigScreen)
    screen.selection_presenter = _selection()
    screen._status_label = FakeLabel()
    screen._on_next = MagicMock()

    screen._handle_next()

    screen._on_next.assert_not_called()

    assert screen._status_label.options == {
        "text": "Select at least one program to continue.",
        "text_color": "#B00020",
    }

    screen.selection_presenter.can_proceed.return_value = True

    screen._handle_next()

    screen._on_next.assert_called_once()


def test_fill_details_renders_group_heading_and_course_metadata() -> None:
    module, fake_ctk = load_screen_module("programConfigScreen.py")

    screen = object.__new__(module.ProgramConfigScreen)
    frame = FakeFrame()

    details = ProgramDetails(
        program_number="83101",
        course_count=1,
        groups=[
            SemesterGroup(
                year=2,
                semester="FALL",
                courses=[
                    CourseDetail(
                        course_number="12345",
                        name="Algorithms",
                        instructor="Dr. Ada",
                        status="Obligatory",
                        evaluation_type="Exam",
                    )
                ],
            )
        ],
    )

    screen._fill_details(frame, details)

    texts = [
        widget.options.get("text")
        for widget in fake_ctk.CTkLabel.created
    ]

    assert "Year 2 - FALL" in texts
    assert "12345  |  Algorithms  |  Obligatory  |  Exam" in texts


def test_fill_details_has_placeholder_for_empty_program() -> None:
    module, fake_ctk = load_screen_module("programConfigScreen.py")

    screen = object.__new__(module.ProgramConfigScreen)

    screen._fill_details(
        FakeFrame(),
        ProgramDetails("83101", 0, []),
    )

    assert widgets_with_text(
        fake_ctk.CTkLabel,
        "No courses found for this program.",
    )


def test_constructor_includes_back_button_when_callback_is_supplied() -> None:
    module, fake_ctk = load_screen_module("programConfigScreen.py")

    on_back = MagicMock()

    module.ProgramConfigScreen(
        fake_ctk.CTkFrame(),
        _selection(["83101"]),
        MagicMock(),
        on_back=on_back,
    )

    back_buttons = [
        button
        for button in fake_ctk.CTkButton.created
        if button.options.get("text") == "Back"
    ]

    assert len(back_buttons) == 1

    back_buttons[0].invoke()

    on_back.assert_called_once()