from unittest.mock import MagicMock
from types import SimpleNamespace

from gui.exportPresenter import ExportResult
from gui.scheduleNavigationPresenter import (
    ExamRow,
    MetricsSummaryView,
    MoedSection,
    ResultMode,
    SystemView,
)
from ranking_settings import RankingCriterion

from .gui_test_support import FakeButton, FakeLabel, load_screen_module, widgets_with_text


def _exam(
    number="12345",
    name="Algorithms",
    exam_date="05-01-2026",
    status="Obligatory",
    programs="83101",
) -> ExamRow:
    return ExamRow(
        exam_date=exam_date,
        course_number=number,
        course_name=name,
        instructor="Dr. Ada",
        status=status,
        program_numbers=programs,
    )


def _presenter(view):
    presenter = MagicMock()
    presenter.current_view.return_value = view
    presenter.relevant_months.return_value = [(2026, 1)]
    presenter.can_go_previous.return_value = False
    presenter.can_go_next.return_value = True
    presenter.is_partial = False
    presenter.systems_seen = 0
    presenter.displayed_count = 0
    presenter.result_mode = ResultMode.UNRANKED_GENERATED

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


def test_next_repaints_calendar_and_ranking_metrics_for_current_ranked_system() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    first_view = SystemView(
        1,
        2,
        [],
        2026,
        {"2026-01-02": [_exam("83002", "Second")]},
        MetricsSummaryView(
            schedule_id=2,
            min_mandatory_gap=9,
            average_all_gap=5.0,
            elective_collision_count=1,
            mandatory_span=8,
            max_exams_per_day=2,
        ),
    )
    second_view = SystemView(
        2,
        2,
        [],
        2026,
        {"2026-01-01": [_exam("83001", "First")]},
        MetricsSummaryView(
            schedule_id=1,
            min_mandatory_gap=2,
            average_all_gap=1.0,
            elective_collision_count=0,
            mandatory_span=3,
            max_exams_per_day=1,
        ),
    )
    presenter = _presenter(first_view)
    presenter.result_mode = ResultMode.FINAL_RANKED
    presenter.current_view.side_effect = [first_view, second_view]
    presenter.can_go_previous.return_value = True
    presenter.can_go_next.return_value = False

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
    )

    screen._handle_next()

    presenter.next.assert_called_once()
    assert screen._counter_label.options["text"] == "System 2 of 2"
    assert screen._exam_cells["2026-01-01"].options["state"] == "normal"
    assert screen._exam_cells["2026-01-02"].options["state"] == "disabled"
    assert screen._ranking_metric_labels["min_mandatory_gap"].options["text"] == "2"
    assert screen._ranking_metric_labels["average_all_gap"].options["text"] == "1.00"


def test_next_refreshes_selected_date_detail_cards() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    first_view = SystemView(
        1,
        2,
        [],
        2026,
        {"2026-01-02": [_exam("83002", "Second", "02-01-2026")]},
    )
    second_view = SystemView(
        2,
        2,
        [],
        2026,
        {"2026-01-01": [_exam("83001", "First", "01-01-2026")]},
    )
    presenter = _presenter(first_view)
    presenter.current_view.side_effect = [first_view, second_view]
    presenter.can_go_previous.return_value = True
    presenter.can_go_next.return_value = False

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
    )

    screen._handle_next()

    assert screen._selected_day_label.options["text"] == "Selected date: 01-01-2026"
    detail_texts = [
        widget.options.get("text")
        for widget in screen._details_body.winfo_children()[0].winfo_children()
    ]
    assert "83001 - First" in detail_texts
    assert "83002 - Second" not in detail_texts


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
        "Type: Mandatory    "
        "Programs: 83101    "
        "Date: 05-01-2026"
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
        if button.options.get("text") == "Save Final System"
    ]

    assert len(back_buttons) == 1
    assert len(save_buttons) == 1

    back_buttons[0].invoke()

    on_back.assert_called_once()


def test_partial_preview_disables_save_and_uses_live_copy() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        2,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )
    presenter = _presenter(view)
    presenter.is_partial = True
    presenter.systems_seen = 120
    presenter.displayed_count = 50

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
        export_presenter=MagicMock(),
    )

    assert screen._save_button.options["state"] == "disabled"
    assert "Live preview" in screen._status_seen_label.options["text"]
    assert "temporary Top 50" in screen._status_seen_label.options["text"]


def test_unranked_generated_results_do_not_show_final_top_50_banner() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        76032,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )
    presenter = _presenter(view)

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
        export_presenter=MagicMock(),
    )

    assert screen._counter_label.options["text"] == "System 1 of 76032"
    assert "FINAL: final Top 50" not in screen._status_seen_label.options.get("text", "")
    assert not screen._status_banner.winfo_ismapped()


def test_final_ranked_results_show_final_ranked_banner_without_top_50_copy() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        76032,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )
    presenter = _presenter(view)
    presenter.result_mode = ResultMode.FINAL_RANKED

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
        export_presenter=MagicMock(),
    )

    assert "Ranking complete" in screen._status_seen_label.options["text"]
    assert "76,032 ranked schedules" in screen._status_seen_label.options["text"]
    assert "Top 50" not in screen._status_seen_label.options["text"]


def test_partial_preview_save_is_blocked_without_file_dialog(monkeypatch) -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen.presenter.is_partial = True
    screen._status_label = FakeLabel()
    screen._export_presenter = MagicMock()

    ask = MagicMock()
    monkeypatch.setattr(module.filedialog, "asksaveasfilename", ask)

    screen._handle_save()

    ask.assert_not_called()
    screen._export_presenter.export_current.assert_not_called()
    assert "temporary live preview" in screen._status_label.options["text"]


def test_constructor_includes_dark_mode_button() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    view = SystemView(
        1,
        1,
        [],
        2026,
        {"2026-01-05": [_exam()]},
    )
    theme_text = {"value": "\u263e"}

    def toggle_theme():
        theme_text["value"] = "\u2600"

    module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
        on_theme_toggle=toggle_theme,
        theme_button_text=lambda: theme_text["value"],
    )

    buttons = widgets_with_text(fake_ctk.CTkButton, "\u263e")
    assert len(buttons) == 1

    buttons[0].invoke()

    assert buttons[0].options["text"] == "\u2600"


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

    assert [
        frame
        for frame in fake_ctk.CTkFrame.created
        if frame.options.get("height") == 320
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
    runner = MagicMock()
    runner.is_running = False
    captured = {}

    def capture_run_with_progress(**kwargs):
        captured.update(kwargs)
        kwargs["task"](SimpleNamespace(is_cancelled=True), lambda _update: None)
        return True

    runner.run_with_progress.side_effect = capture_run_with_progress
    screen._ranking_runner = runner
    screen._ranking_run_id = 0
    screen.after = lambda _ms, callback: callback()
    screen._ranking_criteria = [
        RankingCriterion.max_exams_per_day,
        RankingCriterion.min_mandatory_gap,
    ]
    screen._set_ranking_status = MagicMock()
    screen._refresh = MagicMock()
    screen._grid_built = True
    screen._exam_cells = {"2026-01-05": object()}
    screen._selected_iso_date = "2026-01-05"
    screen._body = MagicMock()

    screen._handle_apply_ranking()

    settings = screen.presenter.rank_progressively.call_args.args[0]
    assert [
        preference.criterion
        for preference in settings.priority_list
    ] == [
        RankingCriterion.max_exams_per_day,
        RankingCriterion.min_mandatory_gap,
    ]
    assert settings.priority_list[0].descending is True
    assert settings.priority_list[1].descending is True
    assert runner.run_with_progress.called
    assert captured["on_started"] is not None
    assert captured["on_progress"] is not None
    assert captured["on_complete"] is not None
    screen.presenter.apply_ranking.assert_not_called()
    screen._refresh.assert_not_called()


def test_apply_ranking_refreshes_displayed_metric_labels() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    before = SystemView(
        1,
        2,
        [],
        2026,
        {"2026-01-01": [_exam("83001", "First")]},
        MetricsSummaryView(
            schedule_id=1,
            min_mandatory_gap=10,
            average_all_gap=3.0,
            elective_collision_count=0,
            mandatory_span=8,
            max_exams_per_day=1,
        ),
    )
    after = SystemView(
        1,
        2,
        [],
        2026,
        {"2026-01-02": [_exam("83002", "Second")]},
        MetricsSummaryView(
            schedule_id=2,
            min_mandatory_gap=4,
            average_all_gap=9.0,
            elective_collision_count=2,
            mandatory_span=12,
            max_exams_per_day=3,
        ),
    )
    presenter = _presenter(before)

    class InlineRunner:
        is_running = False

        def run_with_progress(
            self,
            task,
            on_started=None,
            on_progress=None,
            on_complete=None,
            on_error=None,
        ):
            if on_started is not None:
                on_started()
            update = module.ProgressiveRankingUpdate(
                run_id=1,
                ranked_schedules=["ranked"],
                is_partial=False,
                processed_count=2,
                total_count=2,
                displayed_count=2,
                message="Final Top 2 ranking complete from 2 generated schedule(s).",
            )
            presenter.current_view.return_value = after
            if on_complete is not None:
                on_complete(update)
            return True

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
        ranking_runner=InlineRunner(),
    )
    screen._ranking_criteria = [RankingCriterion.average_all_gap]

    screen._handle_apply_ranking()

    assert screen._ranking_metric_labels["min_mandatory_gap"].options["text"] == "4"
    assert screen._ranking_metric_labels["average_all_gap"].options["text"] == "9.00"
    assert screen._ranking_metric_labels["elective_collision_count"].options["text"] == "2"
    assert screen._ranking_metric_labels["mandatory_span"].options["text"] == "12"
    assert screen._ranking_metric_labels["max_exams_per_day"].options["text"] == "3"


def test_failed_apply_ranking_shows_error_without_refreshing() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    runner = MagicMock()
    runner.is_running = False
    runner.run_with_progress.return_value = False
    screen._ranking_runner = runner
    screen._ranking_run_id = 0
    screen.after = lambda _ms, callback: callback()
    screen._ranking_criteria = [
        RankingCriterion.max_exams_per_day,
    ]
    screen._set_ranking_status = MagicMock()
    screen._refresh = MagicMock()
    screen._grid_built = True
    original_cells = {"2026-01-05": object()}
    screen._exam_cells = original_cells
    screen._selected_iso_date = "2026-01-05"

    screen._handle_apply_ranking()

    screen._set_ranking_status.assert_called_once_with(
        "Ranking is already running.",
        ok=False,
    )
    assert screen._grid_built is True
    assert screen._exam_cells is original_cells
    assert screen._selected_iso_date == "2026-01-05"
    screen._refresh.assert_not_called()


def test_empty_apply_ranking_clears_ranking_synchronously() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen.presenter.apply_ranking.return_value = SimpleNamespace(
        success=True,
        message="Ranking cleared; generation order restored.",
    )
    screen._ranking_runner = MagicMock()
    screen._ranking_runner.is_running = False
    screen._ranking_criteria = []
    screen._set_ranking_status = MagicMock()
    screen._refresh = MagicMock()
    screen._reset_calendar_grid = MagicMock()

    screen._handle_apply_ranking()

    screen.presenter.apply_ranking.assert_called_once()
    screen._ranking_runner.run_with_progress.assert_not_called()
    screen._reset_calendar_grid.assert_called_once()
    screen._refresh.assert_called_once()


def test_apply_ranking_receives_partial_preview_before_final_completion() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    class InlineRunner:
        is_running = False

        def run_with_progress(
            self,
            task,
            on_started=None,
            on_progress=None,
            on_complete=None,
            on_error=None,
        ):
            if on_started is not None:
                on_started()
            result = task(SimpleNamespace(is_cancelled=False), on_progress)
            if on_complete is not None:
                on_complete(result)
            return True

    partial = module.ProgressiveRankingUpdate(
        run_id=1,
        ranked_schedules=["partial"],
        is_partial=True,
        processed_count=10,
        total_count=100,
        displayed_count=1,
        message="Live preview",
    )
    final = module.ProgressiveRankingUpdate(
        run_id=1,
        ranked_schedules=["final"],
        is_partial=False,
        processed_count=100,
        total_count=100,
        displayed_count=1,
        message="Final Top 1",
    )

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen.presenter.rank_progressively.side_effect = (
        lambda _settings, run_id, on_update, **_kwargs: (
            on_update(partial),
            final,
        )[1]
    )
    screen._ranking_runner = InlineRunner()
    screen._ranking_run_id = 0
    screen.after = lambda _ms, callback: callback()
    screen._ranking_criteria = [RankingCriterion.max_exams_per_day]
    screen._set_ranking_status = MagicMock()
    screen._apply_ranking_button = FakeButton()
    screen.push_live_update = MagicMock()

    screen._handle_apply_ranking()

    assert screen.push_live_update.call_args_list[0].args == (
        ["partial"],
    )
    assert screen.push_live_update.call_args_list[0].kwargs == {
        "is_partial": True,
        "systems_seen": 10,
    }
    assert screen.push_live_update.call_args_list[1].args == (
        ["final"],
    )
    assert screen.push_live_update.call_args_list[1].kwargs == {
        "is_partial": False,
        "systems_seen": 100,
    }


def test_apply_ranking_returns_without_running_ranking_when_runner_defers_work() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    class DeferredRunner:
        is_running = False

        def __init__(self):
            self.task = None

        def run_with_progress(self, task, **_kwargs):
            self.task = task
            return True

    runner = DeferredRunner()
    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen._ranking_runner = runner
    screen._ranking_run_id = 0
    screen.after = lambda _ms, callback: callback()
    screen._ranking_criteria = [RankingCriterion.max_exams_per_day]
    screen._set_ranking_status = MagicMock()
    screen._apply_ranking_button = FakeButton()

    screen._handle_apply_ranking()

    assert runner.task is not None
    screen.presenter.rank_progressively.assert_not_called()


def test_stale_ranking_updates_are_ignored() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen._ranking_run_id = 2
    screen.push_live_update = MagicMock()
    screen._set_ranking_status = MagicMock()
    screen._apply_ranking_button = FakeButton()

    stale = module.ProgressiveRankingUpdate(
        run_id=1,
        ranked_schedules=["old"],
        is_partial=True,
        processed_count=10,
        total_count=100,
        displayed_count=1,
        message="old",
    )
    fresh = module.ProgressiveRankingUpdate(
        run_id=2,
        ranked_schedules=["new"],
        is_partial=True,
        processed_count=20,
        total_count=100,
        displayed_count=1,
        message="new",
    )

    screen._handle_ranking_update(stale)
    screen._handle_ranking_update(fresh)

    screen.push_live_update.assert_called_once_with(
        ["new"],
        is_partial=True,
        systems_seen=20,
    )


def test_live_preview_update_reuses_existing_calendar_grid() -> None:
    module, _ = load_screen_module("scheduleNavigationScreen.py")

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen.presenter = MagicMock()
    screen.presenter.has_schedules.return_value = True
    screen._grid_built = True
    screen._build_relevant_months_grid = MagicMock()
    screen._reset_calendar_grid = MagicMock()
    screen._refresh = MagicMock()
    screen._update_status_banner = MagicMock()

    screen.push_live_update(["preview"], is_partial=True, systems_seen=100)

    screen.presenter.update_schedules.assert_called_once_with(
        ["preview"],
        is_partial=True,
        systems_seen=100,
        displayed_count=1,
    )
    screen._reset_calendar_grid.assert_not_called()
    screen._build_relevant_months_grid.assert_called_once()
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


def test_selected_date_panel_title_matches_filtered_content() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    selected_exam = _exam("83001", "Selected", "05-01-2026", "Elective", "Aleph")
    other_exam = _exam("83002", "Other", "08-02-2026", "Obligatory", "Bet")
    view = SystemView(
        1,
        1,
        [],
        2026,
        {
            "2026-01-05": [selected_exam],
            "2026-02-08": [other_exam],
        },
    )
    presenter = _presenter(view)
    presenter.relevant_months.return_value = [(2026, 1), (2026, 2)]

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        presenter,
    )
    screen._select_day("2026-01-05")

    assert screen._selected_day_label.options["text"] == "Selected date: 05-01-2026"
    detail_texts = [
        widget.options.get("text")
        for widget in screen._details_body.winfo_children()[0].winfo_children()
    ]
    assert "83001 - Selected" in detail_texts
    assert "83002 - Other" not in detail_texts
    assert "Type: Elective\nLecturer: Dr. Ada\nPrograms: Aleph\nDate: 05-01-2026" in detail_texts


def test_full_schedule_rows_include_required_exam_details() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    first = _exam("83001", "Algorithms", "05-01-2026", "Obligatory", "83101")
    second = _exam("83002", "Databases", "08-02-2026", "Elective", "83108")
    section = SimpleNamespace(semester="FALL", moed="Aleph", exams=[first, second])

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen._schedule_body = fake_ctk.CTkScrollableFrame()

    screen._render_system_exam_list([section])

    texts = [
        widget.options.get("text")
        for widget in screen._schedule_body.winfo_children()
    ]
    assert "83001 - Algorithms\nType: Mandatory | Programs: 83101 | Date: 05-01-2026" in texts
    assert "83002 - Databases\nType: Elective | Programs: 83108 | Date: 08-02-2026" in texts


def test_selected_date_details_render_many_exam_cards_without_nested_scroll() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    exams = [
        _exam(f"83{i:03d}", f"Course {i}", "05-01-2026")
        for i in range(20)
    ]
    view = SystemView(
        1,
        1,
        [],
        2026,
        {"2026-01-05": exams},
    )

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
    )

    assert "height" not in screen._details_body.options
    assert len(screen._details_body.winfo_children()) == 20
    assert all(
        child.options.get("corner_radius") == 8
        for child in screen._details_body.winfo_children()
    )


def test_full_schedule_remains_the_scrollable_long_content_area() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    exams = [
        _exam(f"83{i:03d}", f"Course {i}", "05-01-2026")
        for i in range(30)
    ]
    section = SimpleNamespace(semester="FALL", moed="Aleph", exams=exams)

    screen = object.__new__(module.ScheduleNavigationScreen)
    screen._schedule_body = fake_ctk.CTkFrame()

    screen._render_system_exam_list([section])

    assert len(screen._schedule_body.winfo_children()) == 31
    assert screen._schedule_body.winfo_children()[1].options["text"].startswith(
        "83000 - Course 0\nType: Mandatory"
    )


def test_full_schedule_rows_are_visible_in_constructed_screen() -> None:
    module, fake_ctk = load_screen_module("scheduleNavigationScreen.py")

    exam = _exam("83001", "Algorithms", "05-01-2026")
    view = SystemView(
        1,
        1,
        [MoedSection("FALL", "Aleph", [exam])],
        2026,
        {"2026-01-05": [exam]},
    )

    screen = module.ScheduleNavigationScreen(
        fake_ctk.CTkFrame(),
        _presenter(view),
    )

    assert screen._schedule_body.options.get("height") is None
    texts = [
        widget.options.get("text")
        for widget in screen._schedule_body.winfo_children()
    ]
    assert "FALL | Aleph" in texts
    assert "83001 - Algorithms\nType: Mandatory | Programs: 83101 | Date: 05-01-2026" in texts


def test_details_card_is_single_scrollable_container() -> None:
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
        frame
        for frame in fake_ctk.CTkFrame.created
        if frame.options.get("height") == 430
    ]
