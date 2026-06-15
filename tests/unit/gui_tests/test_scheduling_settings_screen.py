from types import SimpleNamespace
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
        "Req 2.1 Mandatory Course Gap",
        "Req 2.2 General Exam Gap",
        "Req 2.3 Elective Collision Limit",
        "Req 2.4 Mandatory Exam-Period Span",
        "Req 2.5 Maximum Exams Per Day",
    ):
        assert widgets_with_text(fake_ctk.CTkLabel, expected_text)


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


def test_constructor_restores_values_from_presenter_rows() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.mandatory_gap_days
    presenter = MagicMock()
    presenter.rows.return_value = [
        SimpleNamespace(
            constraint_type=current,
            enabled=current is constraint_type,
            k_text="4" if current is constraint_type else "",
        )
        for current in ThresholdConstraintType
    ]

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        presenter=presenter,
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


def test_toggle_updates_presenter_when_supplied() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.max_exams_per_day
    presenter = MagicMock()
    presenter.rows.return_value = [
        SimpleNamespace(
            constraint_type=current,
            enabled=False,
            k_text="",
        )
        for current in ThresholdConstraintType
    ]

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        presenter=presenter,
    )

    screen._enabled_vars[constraint_type].set(True)
    screen._handle_enabled_toggle(constraint_type)

    presenter.update_enabled.assert_called_with(constraint_type, True)


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
    assert "must be an integer" in screen._error_labels[constraint_type].options["text"]
    assert (
        screen._status_label.options["text"]
        == "Fix the highlighted settings before continuing."
    )
    assert screen._status_label.options["text_color"] == module._ERROR


def test_continue_uses_presenter_save_result() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.max_exams_per_day
    on_next = MagicMock()
    saved_settings = _settings(
        {
            constraint_type: ThresholdConstraintSetting(
                enabled=True,
                k=3,
            )
        }
    )
    presenter = MagicMock()
    presenter.rows.return_value = [
        SimpleNamespace(
            constraint_type=current,
            enabled=False,
            k_text="",
        )
        for current in ThresholdConstraintType
    ]
    presenter.save.return_value = SimpleNamespace(
        success=True,
        message="Settings saved.",
        field_errors={},
        settings=saved_settings,
    )

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        presenter=presenter,
        on_next=on_next,
    )
    screen._enabled_vars[constraint_type].set(True)
    screen._k_entries[constraint_type].insert(0, "3")

    screen._handle_continue()

    presenter.update_enabled.assert_any_call(constraint_type, True)
    presenter.update_k.assert_any_call(constraint_type, "3")
    presenter.save.assert_called_once()
    on_next.assert_called_once_with(saved_settings)
    assert screen._status_label.options["text"] == "Settings saved."


def test_continue_displays_presenter_validation_errors() -> None:
    module, fake_ctk = load_screen_module("schedulingSettingsScreen.py")
    constraint_type = ThresholdConstraintType.elective_conflicts_per_program
    on_next = MagicMock()
    presenter = MagicMock()
    presenter.rows.return_value = [
        SimpleNamespace(
            constraint_type=current,
            enabled=current is constraint_type,
            k_text="abc" if current is constraint_type else "",
        )
        for current in ThresholdConstraintType
    ]
    presenter.save.return_value = SimpleNamespace(
        success=False,
        message="Fix the highlighted settings before continuing.",
        field_errors={constraint_type.value: ["k must be an integer."]},
        settings=None,
    )

    screen = module.SchedulingSettingsScreen(
        fake_ctk.CTkFrame(),
        presenter=presenter,
        on_next=on_next,
    )

    screen._handle_continue()

    on_next.assert_not_called()
    assert "integer" in screen._error_labels[constraint_type].options["text"]
    assert (
        screen._status_label.options["text"]
        == "Fix the highlighted settings before continuing."
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
