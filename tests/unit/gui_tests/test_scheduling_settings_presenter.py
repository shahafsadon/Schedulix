"""Unit tests for SchedulingSettingsPresenter (SCRUM-160)."""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from application.cache_manager import CacheManager
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from gui.presenters import schedulingSettingsPresenter as presenter_module
from gui.presenters.schedulingSettingsPresenter import SchedulingSettingsPresenter


def _settings(
    constraint_type: ThresholdConstraintType,
    *,
    enabled: bool,
    k: int,
) -> SchedulingConstraintSettings:
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[constraint_type] = ThresholdConstraintSetting(
        enabled=enabled,
        k=k,
    )
    return settings


class SchedulingSettingsPresenterTests(unittest.TestCase):
    """Presenter behavior for settings rows, edits, validation, and cache saves."""

    def setUp(self) -> None:
        self._temp_cache_dir = tempfile.TemporaryDirectory()
        self._original_pkl_path = CacheManager._PKL_PATH
        CacheManager._PKL_PATH = (
            Path(self._temp_cache_dir.name) / "internal_data.pkl"
        )

    def tearDown(self) -> None:
        CacheManager._PKL_PATH = self._original_pkl_path
        self._temp_cache_dir.cleanup()

    def test_module_has_no_customtkinter_imports(self) -> None:
        """Presenter must stay free of GUI toolkit dependencies."""
        source = inspect.getsource(presenter_module)
        self.assertNotIn("customtkinter", source)

    def test_rows_load_current_settings_from_cache(self) -> None:
        cache = CacheManager()
        constraint_type = ThresholdConstraintType.mandatory_gap_days
        cache.set_constraint_settings(
            _settings(constraint_type, enabled=True, k=4)
        )

        presenter = SchedulingSettingsPresenter(cache)
        rows = {row.constraint_type: row for row in presenter.rows()}

        row = rows[constraint_type]
        self.assertEqual(row.requirement_id, "Req 2.1")
        self.assertEqual(row.title, "Mandatory Course Gap")
        self.assertTrue(row.enabled)
        self.assertTrue(row.k_input_enabled)
        self.assertEqual(row.k_text, "4")

    def test_rows_include_all_five_requirements(self) -> None:
        rows = SchedulingSettingsPresenter(CacheManager()).rows()

        self.assertEqual(
            {row.constraint_type for row in rows},
            set(ThresholdConstraintType),
        )

    def test_update_enabled_changes_only_draft_state(self) -> None:
        cache = CacheManager()
        constraint_type = ThresholdConstraintType.max_exams_per_day
        presenter = SchedulingSettingsPresenter(cache)

        rows = presenter.update_enabled(constraint_type, True)
        updated = {row.constraint_type: row for row in rows}[constraint_type]

        self.assertTrue(updated.enabled)
        self.assertTrue(updated.k_input_enabled)
        self.assertFalse(
            cache.get_constraint_settings().constraints[constraint_type].enabled
        )
        self.assertTrue(presenter.has_unsaved_changes())

    def test_update_k_changes_draft_text(self) -> None:
        constraint_type = ThresholdConstraintType.any_course_gap_days
        presenter = SchedulingSettingsPresenter(CacheManager())

        rows = presenter.update_k(constraint_type, " 7 ")
        updated = {row.constraint_type: row for row in rows}[constraint_type]

        self.assertEqual(updated.k_text, "7")

    def test_invalid_enabled_k_returns_user_facing_error_without_saving(self) -> None:
        cache = CacheManager()
        constraint_type = ThresholdConstraintType.elective_conflicts_per_program
        presenter = SchedulingSettingsPresenter(cache)
        presenter.update_enabled(constraint_type, True)
        presenter.update_k(constraint_type, "abc")

        result = presenter.save()

        self.assertFalse(result.success)
        self.assertIn("Fix the highlighted settings", result.message)
        self.assertIn(constraint_type.value, result.field_errors)
        self.assertIn("integer", result.field_errors[constraint_type.value][0])
        self.assertFalse(
            cache.get_constraint_settings().constraints[constraint_type].enabled
        )

    def test_disabled_requirement_does_not_require_k_value(self) -> None:
        cache = CacheManager()
        constraint_type = ThresholdConstraintType.any_course_gap_days
        presenter = SchedulingSettingsPresenter(cache)
        presenter.update_k(constraint_type, "not needed")

        result = presenter.save()

        self.assertTrue(result.success)
        saved_setting = cache.get_constraint_settings().constraints[constraint_type]
        self.assertFalse(saved_setting.enabled)
        self.assertEqual(saved_setting.k, 0)

    def test_saving_changed_settings_invalidates_generated_schedules(self) -> None:
        cache = CacheManager()
        cache.set_generated_schedules(["generated"])  # type: ignore[list-item]
        constraint_type = ThresholdConstraintType.max_exams_per_day
        presenter = SchedulingSettingsPresenter(cache)
        presenter.update_enabled(constraint_type, True)
        presenter.update_k(constraint_type, "2")

        result = presenter.save()

        self.assertTrue(result.success)
        self.assertTrue(result.settings_changed)
        self.assertTrue(result.schedules_invalidated)
        self.assertEqual(cache.get_generated_schedules(), [])
        self.assertTrue(
            cache.get_constraint_settings().constraints[constraint_type].enabled
        )

    def test_saving_unchanged_settings_does_not_invalidate_schedules(self) -> None:
        cache = CacheManager()
        cache.set_generated_schedules(["generated"])  # type: ignore[list-item]
        presenter = SchedulingSettingsPresenter(cache)

        result = presenter.save()

        self.assertTrue(result.success)
        self.assertFalse(result.settings_changed)
        self.assertFalse(result.schedules_invalidated)
        self.assertEqual(cache.get_generated_schedules(), ["generated"])

    def test_reload_from_cache_restores_saved_values_after_draft_edits(self) -> None:
        cache = CacheManager()
        constraint_type = ThresholdConstraintType.mandatory_span_days
        cache.set_constraint_settings(
            _settings(constraint_type, enabled=True, k=9)
        )
        presenter = SchedulingSettingsPresenter(cache)
        presenter.update_enabled(constraint_type, False)
        presenter.update_k(constraint_type, "1")

        rows = presenter.reload_from_cache()
        restored = {row.constraint_type: row for row in rows}[constraint_type]

        self.assertTrue(restored.enabled)
        self.assertEqual(restored.k_text, "9")
        self.assertFalse(presenter.has_unsaved_changes())

    def test_unknown_constraint_type_is_rejected(self) -> None:
        presenter = SchedulingSettingsPresenter(CacheManager())

        with self.assertRaises(ValueError):
            presenter.update_enabled("not-a-constraint", True)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
