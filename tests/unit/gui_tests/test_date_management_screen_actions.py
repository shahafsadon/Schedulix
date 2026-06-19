from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from application.commands import CommandResult

from .gui_test_support import (
    FakeEntry,
    FakeFrame,
    FakeLabel,
    load_screen_module,
    widgets_with_text,
)


def _period(
    start=date(2026, 1, 1),
    end=date(2026, 1, 3),
):
    return SimpleNamespace(
        start_date=start,
        end_date=end,
    )


def _presenter(period=None):
    presenter = MagicMock()
    presenter.current_period.return_value = period or _period()
    presenter.is_excluded.return_value = False

    return presenter


def test_months_between_rolls_over_from_december_to_january() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    months = module.DateManagementScreen._months_between(
        date(2025, 12, 20),
        date(2026, 2, 2),
    )

    assert months == [
        (2025, 12),
        (2026, 1),
        (2026, 2),
    ]


def test_constructor_builds_only_in_window_interactive_days() -> None:
    module, fake_ctk = load_screen_module("dateManagementScreen.py")

    screen = module.DateManagementScreen(
        fake_ctk.CTkFrame(),
        _presenter(),
    )

    assert set(screen._day_cells) == {
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    }


def test_click_delegates_to_presenter_then_repaints_and_shows_message() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen.presenter.on_date_clicked.return_value = CommandResult(
        True,
        "excluded",
    )

    screen._paint_days = MagicMock()
    screen._show_message = MagicMock()

    clicked = date(2026, 1, 2)

    screen._handle_day_click(clicked)

    screen.presenter.on_date_clicked.assert_called_once_with(clicked)
    screen._paint_days.assert_called_once()
    screen._show_message.assert_called_once_with(
        "excluded",
        ok=True,
    )


def test_apply_period_rejects_bad_format_without_calling_presenter() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen._start_entry = FakeEntry()
    screen._start_entry.content = "2026/01/01"

    screen._end_entry = FakeEntry()
    screen._end_entry.content = "03-01-2026"

    screen._show_message = MagicMock()

    screen._handle_apply_period()

    screen.presenter.on_edit_period.assert_not_called()

    screen._show_message.assert_called_once_with(
        "Dates must be in DD-MM-YYYY format.",
        ok=False,
    )


def test_apply_period_rebuilds_calendar_after_success() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen.presenter.on_edit_period.return_value = CommandResult(
        True,
        "changed",
    )

    screen._start_entry = FakeEntry()
    screen._start_entry.content = "01-02-2026"

    screen._end_entry = FakeEntry()
    screen._end_entry.content = "07-02-2026"

    screen._rebuild_calendar = MagicMock()
    screen._show_message = MagicMock()

    screen._handle_apply_period()

    screen.presenter.on_edit_period.assert_called_once_with(
        date(2026, 2, 1),
        date(2026, 2, 7),
    )

    screen._rebuild_calendar.assert_called_once()

    screen._show_message.assert_called_once_with(
        "changed",
        ok=True,
    )


def test_rejected_period_edit_resynchronizes_entries() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen.presenter.on_edit_period.return_value = CommandResult(
        False,
        "invalid range",
    )

    screen._start_entry = FakeEntry()
    screen._start_entry.content = "07-02-2026"

    screen._end_entry = FakeEntry()
    screen._end_entry.content = "01-02-2026"

    screen._sync_entries_from_period = MagicMock()
    screen._show_message = MagicMock()

    screen._handle_apply_period()

    screen._sync_entries_from_period.assert_called_once()

    screen._show_message.assert_called_once_with(
        "invalid range",
        ok=False,
    )


def test_undo_rebuilds_and_resynchronizes_on_success() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen.presenter.undo_last.return_value = CommandResult(
        True,
        "restored",
    )

    screen._rebuild_calendar = MagicMock()
    screen._sync_entries_from_period = MagicMock()
    screen._show_message = MagicMock()

    screen._handle_undo()

    screen._rebuild_calendar.assert_called_once()
    screen._sync_entries_from_period.assert_called_once()

    screen._show_message.assert_called_once_with(
        "restored",
        ok=True,
    )


def test_next_callback_is_optional() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen._on_next = None

    screen._handle_next()

    screen._on_next = MagicMock()

    screen._handle_next()

    screen._on_next.assert_called_once()


def test_excluded_day_is_painted_red_and_active_day_green() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen.presenter.is_excluded.side_effect = (
        lambda current_date: current_date == date(2026, 1, 2)
    )

    screen._day_cells = {
        "2026-01-01": FakeLabel(),
        "2026-01-02": FakeLabel(),
    }

    screen._paint_days()

    assert (
        screen._day_cells["2026-01-01"].options["fg_color"]
        == module._ACTIVE_DAY_COLOR
    )

    assert (
        screen._day_cells["2026-01-02"].options["fg_color"]
        == module._EXCLUDED_DAY_COLOR
    )


def test_undo_failure_does_not_rebuild_calendar() -> None:
    module, _ = load_screen_module("dateManagementScreen.py")

    screen = object.__new__(module.DateManagementScreen)
    screen.presenter = _presenter()

    screen.presenter.undo_last.return_value = CommandResult(
        False,
        "Nothing to undo.",
    )

    screen._rebuild_calendar = MagicMock()
    screen._sync_entries_from_period = MagicMock()
    screen._show_message = MagicMock()

    screen._handle_undo()

    screen._rebuild_calendar.assert_not_called()
    screen._sync_entries_from_period.assert_not_called()

    screen._show_message.assert_called_once_with(
        "Nothing to undo.",
        ok=False,
    )


def test_constructor_includes_back_button_when_callback_is_supplied() -> None:
    module, fake_ctk = load_screen_module("dateManagementScreen.py")

    on_back = MagicMock()

    module.DateManagementScreen(
        fake_ctk.CTkFrame(),
        _presenter(),
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


def test_constructor_includes_dark_mode_button() -> None:
    module, fake_ctk = load_screen_module("dateManagementScreen.py")

    theme_text = {"value": "\u263e"}

    def toggle_theme():
        theme_text["value"] = "\u2600"

    module.DateManagementScreen(
        fake_ctk.CTkFrame(),
        _presenter(),
        on_theme_toggle=toggle_theme,
        theme_button_text=lambda: theme_text["value"],
    )

    buttons = widgets_with_text(fake_ctk.CTkButton, "\u263e")
    assert len(buttons) == 1

    buttons[0].invoke()

    assert buttons[0].options["text"] == "\u2600"
