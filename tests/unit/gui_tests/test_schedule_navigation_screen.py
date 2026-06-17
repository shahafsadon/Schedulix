from unittest.mock import MagicMock
from types import SimpleNamespace

from gui.exportPresenter import ExportResult
from gui.scheduleNavigationPresenter import ExamRow, MetricsSummaryView, SystemView
from ranking_settings import RankingCriterion

from .gui_test_support import FakeButton, FakeLabel, load_screen_module


def _exam(
    number="12345",
    name="Algorithms",
) -> ExamRow:
    return ExamRow(
        exam_date="05-01-2026",
        course_number=number,
        course_name=name,
        instructor="Dr. Ada",
        status="Obligatory",
        program_numbers="83101",
    )


def _presenter(view):
    presenter = MagicMock()
    presenter.current_view.return_value = view
    presenter.relevant_months.return_value = [(2026, 1)]
    presenter.can_go_previous.return_value = False
    presenter.can_go_next.return_value = True

    return presenter


def test_empty_state_disables_navigation_and_save() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    presenter = _presenter(None)

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = presenter
    screen._counter_label = FakeLabel()
    screen._prev_button = FakeButton()
    screen._next_button = FakeButton()
    screen._save_button = FakeButton()

    screen._refresh()

    assert screen._counter_label.options["text"] == (
        "No schedules to display."
    )

    assert screen._prev_button.options["state"] == "disabled"
    assert screen._next_button.options["state"] == "disabled"
    assert screen._save_button.options["state"] == "disabled"


def test_constructor_builds_grid_once_and_highlights_current_exam_day() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    exams = [_exam()]

    view = SystemView(
        1,
        2,
        [],
        2026,
        {"2026-01-05": exams},
    )

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
    )

    assert screen._grid_built
    assert screen._counter_label.options["text"] == "System 1 of 2"

    assert (
        screen._exam_cells["2026-01-05"].options["state"]
        == "normal"
    )

    assert (
        screen._exam_cells["2026-01-06"].options["state"]
        == "disabled"
    )

    build = MagicMock()
    screen._build_relevant_months_grid = build

    screen._refresh()

    build.assert_not_called()


def test_next_and_previous_delegate_then_refresh() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen._refresh = MagicMock()

    screen._handle_next()
    screen._handle_previous()

    screen.presenter.next.assert_called_once()
    screen.presenter.previous.assert_called_once()

    assert screen._refresh.call_count == 2


def test_painted_exam_day_opens_popup_with_bound_date_and_rows() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)

    screen._exam_cells = {
        "2026-01-05": FakeButton(),
        "2026-01-06": FakeButton(),
    }

    screen._show_day_popup = MagicMock()

    exams = [_exam()]

    screen._paint_exam_days({"2026-01-05": exams})
    screen._exam_cells["2026-01-05"].invoke()

    screen._show_day_popup.assert_called_once_with(
        "2026-01-05",
        exams,
    )

    assert (
        screen._exam_cells["2026-01-06"].options["state"]
        == "disabled"
    )


def test_save_cancel_is_neutral_not_red(monkeypatch) -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen._export_presenter = MagicMock()

    screen._export_presenter.export_current.return_value = ExportResult(
        False,
        "Export cancelled.",
    )

    screen._status_label = FakeLabel()
    screen.winfo_toplevel = lambda: object()

    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: "",
    )

    screen._handle_save()

    screen._export_presenter.export_current.assert_called_once_with(None)

    assert screen._status_label.options == {
        "text": "Export cancelled.",
        "text_color": "#666666",
    }


def test_save_success_is_green_and_failure_is_red(monkeypatch) -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen._export_presenter = MagicMock()
    screen._status_label = FakeLabel()
    screen.winfo_toplevel = lambda: object()

    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: "/tmp/out.txt",
    )

    screen._export_presenter.export_current.return_value = ExportResult(
        True,
        "saved",
    )

    screen._handle_save()

    assert screen._status_label.options == {
        "text": "saved",
        "text_color": "#2e7d32",
    }

    screen._export_presenter.export_current.return_value = ExportResult(
        False,
        "disk full",
    )

    screen._handle_save()

    assert screen._status_label.options == {
        "text": "disk full",
        "text_color": "#B00020",
    }


def test_popup_lists_exam_course_and_requirement_details() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.winfo_toplevel = lambda: "root"

    screen._show_day_popup(
        "2026-01-05",
        [_exam()],
    )

    texts = [
        widget.options.get("text")
        for widget in fake_ctk.CTkLabel.created
    ]

    assert "Exams scheduled on 2026-01-05" in texts
    assert "12345  -  Algorithms" in texts

    assert (
        "Instructor: Dr. Ada    "
        "Requirement: Obligatory    "
        "Programs: 83101"
    ) in texts


def test_constructor_includes_back_and_save_buttons_when_presenters_are_supplied() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        1,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )

    on_back = MagicMock()
    export_presenter = MagicMock()

    module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
        export_presenter=export_presenter,
        on_back=on_back,
    )

    back_buttons = [
        button
        for button in fake_ctk.CTkButton.created
        if button.options.get("text") == "Back"
    ]

    save_buttons = [
        button
        for button in fake_ctk.CTkButton.created
        if button.options.get("text") == "Save System"
    ]

    assert len(back_buttons) == 1
    assert len(save_buttons) == 1

    back_buttons[0].invoke()

    on_back.assert_called_once()


def test_constructor_builds_ranking_controls() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        1,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )

    module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
    )

    assert [
        button
        for button in fake_ctk.CTkButton.created
        if button.options.get("text") == "Apply Ranking"
    ]

    assert [
        label
        for label in fake_ctk.CTkLabel.created
        if label.options.get("text") == "Ranking"
    ]


def test_add_ranking_criterion_prevents_duplicates() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        1,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )
    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
    )

    label = module._RANKING_LABELS[RankingCriterion.min_mandatory_gap]
    screen._criterion_selector.set(label)

    screen._handle_add_ranking_criterion()
    screen._handle_add_ranking_criterion()

    assert screen._ranking_criteria == [
        RankingCriterion.min_mandatory_gap,
    ]
    assert screen._ranking_status_label.options["text"] == (
        "This criterion is already active."
    )
    assert screen._ranking_status_label.options["text_color"] == "#B00020"


def test_ranking_criteria_can_move_and_be_removed() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        1,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )
    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
    )

    screen._ranking_criteria = [
        RankingCriterion.min_mandatory_gap,
        RankingCriterion.max_exams_per_day,
    ]

    screen._handle_move_ranking_criterion(
        RankingCriterion.max_exams_per_day,
        -1,
    )

    assert screen._ranking_criteria == [
        RankingCriterion.max_exams_per_day,
        RankingCriterion.min_mandatory_gap,
    ]

    screen._handle_remove_ranking_criterion(
        RankingCriterion.min_mandatory_gap,
    )

    assert screen._ranking_criteria == [
        RankingCriterion.max_exams_per_day,
    ]


def test_apply_ranking_delegates_without_generation_and_refreshes() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen.presenter.apply_ranking.return_value = SimpleNamespace(
        success=True,
        message="Ranking applied.",
    )
    screen._ranking_criteria = [
        RankingCriterion.max_exams_per_day,
        RankingCriterion.min_mandatory_gap,
    ]
    screen._set_ranking_status = MagicMock()
    screen._refresh = MagicMock()
    screen._grid_built = True
    screen._exam_cells = {"2026-01-05": object()}
    screen._selected_iso_date = "2026-01-05"

    screen._handle_apply_ranking()

    settings = screen.presenter.apply_ranking.call_args.args[0]
    assert [
        preference.criterion
        for preference in settings.priority_list
    ] == [
        RankingCriterion.max_exams_per_day,
        RankingCriterion.min_mandatory_gap,
    ]
    assert settings.priority_list[0].descending is True
    assert settings.priority_list[1].descending is True
    assert screen._grid_built is False
    assert screen._exam_cells == {}
    assert screen._selected_iso_date is None
    screen._refresh.assert_called_once()


def test_ranking_metric_values_are_rendered_for_current_system() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen._ranking_metric_labels = {
        "min_mandatory_gap": FakeLabel(),
        "average_all_gap": FakeLabel(),
        "elective_collision_count": FakeLabel(),
        "mandatory_span": FakeLabel(),
        "max_exams_per_day": FakeLabel(),
    }

    screen._refresh_ranking_metrics(
        MetricsSummaryView(
            schedule_id=1,
            min_mandatory_gap=3,
            average_all_gap=4.125,
            elective_collision_count=2,
            mandatory_span=8,
            max_exams_per_day=5,
        )
    )

    assert screen._ranking_metric_labels["min_mandatory_gap"].options["text"] == "3"
    assert screen._ranking_metric_labels["average_all_gap"].options["text"] == "4.12"
    assert screen._ranking_metric_labels["elective_collision_count"].options["text"] == "2"
    assert screen._ranking_metric_labels["mandatory_span"].options["text"] == "8"
    assert screen._ranking_metric_labels["max_exams_per_day"].options["text"] == "5"


def test_exam_date_missing_from_grid_is_ignored_defensively() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)

    screen._exam_cells = {
        "2026-01-05": FakeButton(),
    }

    screen._paint_exam_days(
        {"2027-02-01": [_exam()]}
    )

    assert (
        screen._exam_cells["2026-01-05"].options["state"]
        == "disabled"
    )
