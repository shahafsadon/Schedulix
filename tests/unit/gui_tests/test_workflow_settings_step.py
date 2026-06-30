"""Workflow tests for the Part 3 scheduling-settings step (SCRUM-161)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from application.cache_manager import CacheManager
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import ExamPeriod
from ranking_settings import RankingSettings

from .gui_test_support import FakeFrame, make_fake_ctk


def _load_workflow_module():
    project_root = Path(__file__).resolve().parents[3]
    source = project_root / "src" / "gui" / "workflow" / "workflowApp.py"

    spec = importlib.util.spec_from_file_location(
        "_headless_workflow_app",
        source,
    )
    module = importlib.util.module_from_spec(spec)
    fake_ctk = make_fake_ctk()

    with patch.dict(sys.modules, {"customtkinter": fake_ctk}):
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module, fake_ctk


def _workflow_shell(module):
    workflow = object.__new__(module.SchedulixWorkflow)
    workflow._set_window_title = MagicMock()
    workflow._set_screen = MagicMock()
    workflow.show_program_config = MagicMock()
    workflow.show_scheduling_settings = MagicMock()
    workflow.show_date_management = MagicMock()
    workflow.show_output_navigation = MagicMock()
    workflow._settings_presenter = None
    workflow._theme_mode = "Light"
    return workflow


def _install_settings_modules(
    presenter_cls,
    screen_cls,
):
    presenter_module = ModuleType("gui.presenters.schedulingSettingsPresenter")
    presenter_module.SchedulingSettingsPresenter = presenter_cls
    screen_module = ModuleType("gui.screens.schedulingSettingsScreen")
    screen_module.SchedulingSettingsScreen = screen_cls

    return patch.dict(
        sys.modules,
        {
            "gui.presenters.schedulingSettingsPresenter": presenter_module,
            "gui.screens.schedulingSettingsScreen": screen_module,
        },
    )


def _isolated_cache() -> tuple[CacheManager, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    CacheManager._PKL_PATH = Path(tmp.name) / "internal_data.pkl"
    return CacheManager(), tmp


def test_program_selection_next_persists_selection_then_opens_settings() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()
    workflow._program_selection = MagicMock()
    workflow._program_selection.can_proceed.return_value = True
    workflow._program_selection.selected_programs = ["83101"]

    module.SchedulixWorkflow._handle_program_selection_next(workflow)

    workflow.cache.set_selected_programs.assert_called_once_with(["83101"])
    workflow.show_scheduling_settings.assert_called_once()
    workflow.show_date_management.assert_not_called()


def test_program_selection_next_stays_put_when_selection_is_invalid() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()
    workflow._program_selection = MagicMock()
    workflow._program_selection.can_proceed.return_value = False

    module.SchedulixWorkflow._handle_program_selection_next(workflow)

    workflow.cache.set_selected_programs.assert_not_called()
    workflow.show_scheduling_settings.assert_not_called()


def test_settings_step_builds_presenter_and_screen_with_shared_cache() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()

    class FakePresenter:
        instances = []

        def __init__(self, cache_manager):
            self.cache_manager = cache_manager
            FakePresenter.instances.append(self)

    class FakeScreen:
        instances = []

        def __init__(
            self,
            master,
            presenter,
            on_back,
            on_next,
        ):
            self.master = master
            self.presenter = presenter
            self.on_back = on_back
            self.on_next = on_next
            FakeScreen.instances.append(self)

    with _install_settings_modules(FakePresenter, FakeScreen):
        module.SchedulixWorkflow.show_scheduling_settings(workflow)

    workflow._set_window_title.assert_called_once_with(
        "Schedulix - Scheduling Settings"
    )
    workflow._set_screen.assert_called_once_with(FakeScreen.instances[0])
    assert FakePresenter.instances[0].cache_manager is workflow.cache
    assert FakeScreen.instances[0].presenter is FakePresenter.instances[0]
    assert FakeScreen.instances[0].on_back is workflow.show_program_config
    assert FakeScreen.instances[0].on_next.__name__ == "_handle_settings_next"


def test_settings_step_passes_theme_toggle_when_screen_accepts_it() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()

    class FakePresenter:
        def __init__(self, cache_manager):
            self.cache_manager = cache_manager

    class FakeScreen:
        instances = []

        def __init__(
            self,
            master,
            presenter,
            on_back,
            on_next,
            on_theme_toggle,
            theme_button_text,
        ):
            self.on_theme_toggle = on_theme_toggle
            self.theme_button_text = theme_button_text
            FakeScreen.instances.append(self)

    with _install_settings_modules(FakePresenter, FakeScreen):
        module.SchedulixWorkflow.show_scheduling_settings(workflow)

    assert FakeScreen.instances[0].on_theme_toggle.__self__ is workflow
    assert (
        FakeScreen.instances[0].on_theme_toggle.__func__
        is module.SchedulixWorkflow.toggle_theme
    )
    assert FakeScreen.instances[0].theme_button_text.__self__ is workflow
    assert (
        FakeScreen.instances[0].theme_button_text.__func__
        is module.SchedulixWorkflow.theme_button_text
    )


def test_workflow_theme_toggle_updates_customtkinter_mode() -> None:
    module, fake_ctk = _load_workflow_module()
    workflow = _workflow_shell(module)

    assert module.SchedulixWorkflow.theme_button_text(workflow) == "\u263e"

    result = module.SchedulixWorkflow.toggle_theme(workflow)

    assert result == "Dark"
    assert fake_ctk.get_appearance_mode() == "Dark"
    assert module.SchedulixWorkflow.theme_button_text(workflow) == "\u2600"


def test_settings_step_falls_back_to_message_when_components_are_missing() -> None:
    module, fake_ctk = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()

    with patch.object(
        module,
        "import_module",
        side_effect=ModuleNotFoundError("settings components missing"),
    ):
        module.SchedulixWorkflow.show_scheduling_settings(workflow)

    workflow._set_screen.assert_called_once()
    texts = [
        widget.options.get("text")
        for widget in fake_ctk.CTkLabel.created
    ]
    assert "Scheduling Settings Unavailable" in texts


def test_invalid_presenter_save_blocks_date_management() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow._settings_presenter = MagicMock()
    workflow._settings_presenter.save.return_value = SimpleNamespace(
        success=False,
    )

    module.SchedulixWorkflow._handle_settings_next(workflow)

    workflow._settings_presenter.save.assert_called_once()
    workflow.show_date_management.assert_not_called()


def test_valid_presenter_save_continues_to_date_management() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow._settings_presenter = MagicMock()
    workflow._settings_presenter.save.return_value = SimpleNamespace(
        success=True,
    )

    module.SchedulixWorkflow._handle_settings_next(workflow)

    workflow.show_date_management.assert_called_once()


def test_unchanged_settings_do_not_invalidate_generated_schedules() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    original_path = CacheManager._PKL_PATH
    cache, tmp = _isolated_cache()
    workflow.cache = cache

    try:
        cache.set_generated_schedules(["generated"])  # type: ignore[list-item]
        settings = SchedulingConstraintSettings.default_configuration()

        module.SchedulixWorkflow._handle_settings_next(workflow, settings)

        assert cache.get_generated_schedules() == ["generated"]
        workflow.show_date_management.assert_called_once()
    finally:
        CacheManager._PKL_PATH = original_path
        tmp.cleanup()


def test_changed_settings_invalidate_generated_schedules_once() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    original_path = CacheManager._PKL_PATH
    cache, tmp = _isolated_cache()
    workflow.cache = cache

    try:
        cache.set_generated_schedules(["generated"])  # type: ignore[list-item]
        settings = SchedulingConstraintSettings.default_configuration()
        settings.constraints[ThresholdConstraintType.max_exams_per_day] = (
            ThresholdConstraintSetting(enabled=True, k=2)
        )

        module.SchedulixWorkflow._handle_settings_next(workflow, settings)

        assert cache.get_generated_schedules() == []
        workflow.show_date_management.assert_called_once()
    finally:
        CacheManager._PKL_PATH = original_path
        tmp.cleanup()


def test_date_management_back_returns_to_settings_step() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()
    workflow.cache.get_exam_periods.return_value = [
        ExamPeriod(
            semester="FALL",
            moed="Aleph",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        )
    ]
    workflow.cache.get_courses.return_value = []

    class FakeDateManagementScreen(FakeFrame):
        instances = []

        def __init__(self, master, **kwargs):
            super().__init__(master)
            self.kwargs = kwargs
            FakeDateManagementScreen.instances.append(self)

    module.DateManagementScreen = FakeDateManagementScreen

    module.SchedulixWorkflow.show_date_management(workflow)

    assert (
        FakeDateManagementScreen.instances[0].kwargs["on_back"]
        is workflow.show_scheduling_settings
    )


def test_output_navigation_passes_active_ranking_to_presenter() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    ranking_settings = RankingSettings([])
    workflow.cache = MagicMock()
    generated = [f"generated-{index}" for index in range(60)]
    workflow.cache.get_generated_schedules.return_value = generated
    workflow.cache.get_ranked_schedules.return_value = ["ranked"]
    workflow.cache.get_result_mode.return_value = "final_ranked"
    workflow.cache.get_ranking_settings.return_value = ranking_settings

    class FakeNavigationPresenter:
        instances = []

        def __init__(
            self,
            schedules,
            cache_manager=None,
            active_ranking=None,
            result_mode=None,
        ):
            self.schedules = schedules
            self.cache_manager = cache_manager
            self.active_ranking = active_ranking
            self.result_mode = result_mode
            FakeNavigationPresenter.instances.append(self)

    class FakeExportPresenter:
        def __init__(self, navigation_presenter):
            self.navigation_presenter = navigation_presenter

    class FakeScheduleNavigationScreen(FakeFrame):
        instances = []

        def __init__(self, master, **kwargs):
            super().__init__(master)
            self.kwargs = kwargs
            FakeScheduleNavigationScreen.instances.append(self)

    module.ScheduleNavigationPresenter = FakeNavigationPresenter
    module.ExportPresenter = FakeExportPresenter
    module.ScheduleNavigationScreen = FakeScheduleNavigationScreen

    module.SchedulixWorkflow.show_output_navigation(workflow)

    presenter = FakeNavigationPresenter.instances[0]
    assert presenter.schedules == ["ranked"]
    assert presenter.cache_manager is workflow.cache
    assert presenter.active_ranking is ranking_settings
    assert presenter.result_mode == "final_ranked"
    workflow._set_screen.assert_called_once_with(
        FakeScheduleNavigationScreen.instances[0]
    )


def test_output_navigation_uses_generated_schedules_until_ranking_is_final() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()
    generated = [f"generated-{index}" for index in range(60)]
    workflow.cache.get_generated_schedules.return_value = generated
    workflow.cache.get_ranked_schedules.return_value = ["preview"]
    workflow.cache.get_result_mode.return_value = "unranked_generated"
    workflow.cache.get_ranking_settings.return_value = RankingSettings([])

    class FakeNavigationPresenter:
        instances = []

        def __init__(
            self,
            schedules,
            cache_manager=None,
            active_ranking=None,
            result_mode=None,
        ):
            self.schedules = schedules
            self.result_mode = result_mode
            FakeNavigationPresenter.instances.append(self)

    class FakeExportPresenter:
        def __init__(self, navigation_presenter):
            self.navigation_presenter = navigation_presenter

    class FakeScheduleNavigationScreen(FakeFrame):
        def __init__(self, master, **kwargs):
            super().__init__(master)

    module.ScheduleNavigationPresenter = FakeNavigationPresenter
    module.ExportPresenter = FakeExportPresenter
    module.ScheduleNavigationScreen = FakeScheduleNavigationScreen

    module.SchedulixWorkflow.show_output_navigation(workflow)

    presenter = FakeNavigationPresenter.instances[0]
    assert presenter.schedules == generated[:50]
    assert presenter.result_mode == "unranked_generated"


def test_output_navigation_accepts_final_ranked_results_without_generated_cache() -> None:
    module, _ = _load_workflow_module()
    workflow = _workflow_shell(module)
    workflow.cache = MagicMock()
    workflow.cache.get_generated_schedules.return_value = []
    workflow.cache.get_ranked_schedules.return_value = ["ranked-preview"]
    workflow.cache.get_result_mode.return_value = "final_ranked"
    workflow.cache.get_ranking_settings.return_value = RankingSettings([])

    class FakeNavigationPresenter:
        instances = []

        def __init__(
            self,
            schedules,
            cache_manager=None,
            active_ranking=None,
            result_mode=None,
        ):
            self.schedules = schedules
            self.result_mode = result_mode
            FakeNavigationPresenter.instances.append(self)

    class FakeExportPresenter:
        def __init__(self, navigation_presenter):
            self.navigation_presenter = navigation_presenter

    class FakeScheduleNavigationScreen(FakeFrame):
        instances = []

        def __init__(self, master, **kwargs):
            super().__init__(master)
            FakeScheduleNavigationScreen.instances.append(self)

    module.ScheduleNavigationPresenter = FakeNavigationPresenter
    module.ExportPresenter = FakeExportPresenter
    module.ScheduleNavigationScreen = FakeScheduleNavigationScreen

    module.SchedulixWorkflow.show_output_navigation(workflow)

    presenter = FakeNavigationPresenter.instances[0]
    assert presenter.schedules == ["ranked-preview"]
    assert presenter.result_mode == "final_ranked"
    workflow._set_screen.assert_called_once_with(
        FakeScheduleNavigationScreen.instances[0]
    )
