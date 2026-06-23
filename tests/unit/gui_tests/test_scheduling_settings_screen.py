from unittest.mock import MagicMock

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)

from .gui_test_support import load_screen_module, widgets_with_text


def _settings(
    overrides: dict[ThresholdConstraintType, ThresholdConstraintSetting],
) -> SchedulingConstraintSettings:
    settings = SchedulingConstraintSettings.default_configuration()
    for constraint_type, setting in overrides.items():
        settings.constraints[constraint_type] = setting
    return settings


def test_constructor_builds_all_requirement_rows_disabled_by_default() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")

    screen = module.SchedulingSettingsScreen(fake_ctk.CTkFrame())

    assert set(screen._enabled_vars) == set(ThresholdConstraintType)
    assert set(screen._k_entries) == set(ThresholdConstraintType)
    assert set(screen._error_labels) == set(ThresholdConstraintType)

    for entry in screen._k_entries.values():
        assert entry.options["state"] == "disabled"

    for expected_text in (
        "Minimum days between mandatory exams",
        "Minimum days between any exams",
        "Maximum elective course conflicts",
        "Minimum spread between first and last mandatory exam",
        "Maximum exams on the same day",
        "Days",
        "Max Conflicts",
        "Max Exams",
    ):
        assert widgets_with_text(fake_ctk.CTkLabel, expected_text)

    visible_texts = {
        widget.options.get("text")
        for widget in fake_ctk.CTkLabel.created
    }
    assert not any(
        isinstance(text, str) and "Req 2." in text
        for text in visible_texts
    )
    assert "k value" not in visible_texts


def test_constructor_restores_saved_enabled_values() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.mandatory_gap_days

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        initial_settings=_settings(
            {
                constraint_type: ThresholdConstraintSetting(
                    enabled=True,
                    k=4,
                )
            }
        ),
    )

    assert screen._enabled_vars[constraint_type].get() is True
    assert screen._k_entries[constraint_type].content == "4"
    assert screen._k_entries[constraint_type].options["state"] == "normal"


def test_toggle_disables_and_enables_matching_k_field() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.max_exams_per_day

    screen = module.SchedulingSettingsScreen(fake_ctk.CTkFrame())

    screen._enabled_vars[constraint_type].set(True)
    screen._handle_enabled_toggle(constraint_type)

    assert screen._k_entries[constraint_type].options["state"] == "normal"

    screen._enabled_vars[constraint_type].set(False)
    screen._handle_enabled_toggle(constraint_type)

    assert screen._k_entries[constraint_type].options["state"] == "disabled"


def test_continue_blocks_invalid_enabled_k_value() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.elective_conflicts_per_program
    on_next = MagicMock()

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        on_next=on_next,
    )
    screen._enabled_vars[constraint_type].set(True)
    screen._handle_enabled_toggle(constraint_type)
    screen._k_entries[constraint_type].insert(0, "abc")

    screen._handle_continue()

    on_next.assert_not_called()
    assert (
        screen._error_labels[constraint_type].options["text"]
        == "Enter a whole number of conflicts."
    )
    assert (
        screen._status_label.options["text"]
        == "Fix this rule before continuing: Maximum elective course conflicts."
    )
    assert screen._status_label.options["text_color"] == module._ERROR
    assert "Threshold" not in screen._error_labels[constraint_type].options["text"]
    assert "k" not in screen._error_labels[constraint_type].options["text"]
    assert "Req 2." not in screen._error_labels[constraint_type].options["text"]


def test_negative_max_exams_shows_visible_user_friendly_error() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.max_exams_per_day
    on_next = MagicMock()

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        on_next=on_next,
    )
    screen._enabled_vars[constraint_type].set(True)
    screen._handle_enabled_toggle(constraint_type)
    screen._k_entries[constraint_type].insert(0, "-1")

    screen._handle_continue()

    on_next.assert_not_called()
    assert (
        screen._error_labels[constraint_type].options["text"]
        == "Enter at least 1 exam."
    )
    assert screen._status_label.options["text"] == (
        "Fix this rule before continuing: Maximum exams on the same day."
    )
    assert "Threshold" not in screen._status_label.options["text"]
    assert "k" not in screen._status_label.options["text"]
    assert "Req 2." not in screen._status_label.options["text"]


def test_zero_day_distance_shows_user_friendly_minimum_error() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.mandatory_gap_days
    on_next = MagicMock()

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        on_next=on_next,
    )
    screen._enabled_vars[constraint_type].set(True)
    screen._handle_enabled_toggle(constraint_type)
    screen._k_entries[constraint_type].insert(0, "0")

    screen._handle_continue()

    on_next.assert_not_called()
    assert (
        screen._error_labels[constraint_type].options["text"]
        == "Enter at least 1 day."
    )
    assert screen._status_label.options["text"] == (
        "Fix this rule before continuing: Minimum days between mandatory exams."
    )


def test_continue_allows_disabled_requirement_without_k_value() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.any_course_gap_days
    on_next = MagicMock()

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        on_next=on_next,
    )
    screen._k_entries[constraint_type].insert(0, "not used")

    screen._handle_continue()

    on_next.assert_called_once()
    saved_settings = on_next.call_args.args[0]
    assert saved_settings.constraints[constraint_type].enabled is False
    assert screen._status_label.options["text"] == "Settings saved."
    assert screen._status_label.options["text_color"] == module._SUCCESS


def test_continue_passes_valid_settings_to_callback() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.max_exams_per_day
    on_next = MagicMock()

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        on_next=on_next,
    )
    screen._enabled_vars[constraint_type].set(True)
    screen._handle_enabled_toggle(constraint_type)
    screen._k_entries[constraint_type].insert(0, "3")

    screen._handle_continue()

    saved_settings = on_next.call_args.args[0]
    saved_setting = saved_settings.constraints[constraint_type]

    assert saved_setting.enabled is True
    assert saved_setting.k == 3


def test_constructor_includes_back_button_when_callback_is_supplied() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    on_back = MagicMock()

    module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
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
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")

    theme_text = {"value": "\u263e"}

    def toggle_theme():
        theme_text["value"] = "\u2600"

    module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        on_theme_toggle=toggle_theme,
        theme_button_text=lambda: theme_text["value"],
    )

    buttons = widgets_with_text(fake_ctk.CTkButton, "\u263e")
    assert len(buttons) == 1

    buttons[0].invoke()

    assert buttons[0].options["text"] == "\u2600"
