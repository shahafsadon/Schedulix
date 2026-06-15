"""Presenter for Part 3 threshold scheduling settings."""
from __future__ import annotations

from dataclasses import dataclass, field

from application.cache_manager import CacheManager
from application.settings_validator import SchedulingSettingsValidator
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)


_REQUIREMENT_COPY: dict[ThresholdConstraintType, tuple[str, str, str]] = {
    ThresholdConstraintType.mandatory_gap_days: (
        "Req 2.1",
        "Mandatory Course Gap",
        "Minimum days between mandatory exams that share a program and year.",
    ),
    ThresholdConstraintType.any_course_gap_days: (
        "Req 2.2",
        "General Exam Gap",
        "Minimum days between any exams that share a program and year.",
    ),
    ThresholdConstraintType.elective_conflicts_per_program: (
        "Req 2.3",
        "Elective Collision Limit",
        "Maximum same-date elective collisions allowed inside one program.",
    ),
    ThresholdConstraintType.mandatory_span_days: (
        "Req 2.4",
        "Mandatory Exam-Period Span",
        "Minimum spread, in days, for mandatory exams in each period group.",
    ),
    ThresholdConstraintType.max_exams_per_day: (
        "Req 2.5",
        "Maximum Exams Per Day",
        "Maximum total exams that may be placed on a single calendar day.",
    ),
}


@dataclass(frozen=True)
class SchedulingSettingRow:
    """One threshold requirement in display-ready form."""

    constraint_type: ThresholdConstraintType
    key: str
    requirement_id: str
    title: str
    description: str
    enabled: bool
    k_text: str
    k_input_enabled: bool


@dataclass(frozen=True)
class SchedulingSettingsSaveResult:
    """Display-ready outcome of saving threshold settings."""

    success: bool
    message: str
    settings_changed: bool = False
    schedules_invalidated: bool = False
    field_errors: dict[str, list[str]] = field(default_factory=dict)
    settings: SchedulingConstraintSettings | None = None


class SchedulingSettingsPresenter:
    """Owns settings-screen state, validation, and persistence."""

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        validator: SchedulingSettingsValidator | None = None,
    ) -> None:
        self._cache = cache_manager or CacheManager()
        self._validator = validator or SchedulingSettingsValidator()
        self._enabled: dict[ThresholdConstraintType, bool] = {}
        self._k_text: dict[ThresholdConstraintType, str] = {}
        self.reload_from_cache()

    def rows(self) -> list[SchedulingSettingRow]:
        """Return all threshold settings as view-ready rows."""
        return [
            self._row_for(constraint_type)
            for constraint_type in ThresholdConstraintType
        ]

    def update_enabled(
        self,
        constraint_type: ThresholdConstraintType,
        enabled: bool,
    ) -> list[SchedulingSettingRow]:
        """Record an enable/disable edit and return refreshed rows."""
        self._require_known_constraint(constraint_type)
        self._enabled[constraint_type] = bool(enabled)
        return self.rows()

    def update_k(
        self,
        constraint_type: ThresholdConstraintType,
        value: str | int,
    ) -> list[SchedulingSettingRow]:
        """Record a k-input edit and return refreshed rows."""
        self._require_known_constraint(constraint_type)
        self._k_text[constraint_type] = str(value).strip()
        return self.rows()

    def save(self) -> SchedulingSettingsSaveResult:
        """Validate and persist the current draft settings."""
        settings = self._settings_from_draft()
        validation = self._validator.validate_constraint_settings(settings)

        if not validation.is_valid:
            return SchedulingSettingsSaveResult(
                success=False,
                message="Fix the highlighted settings before continuing.",
                field_errors=self._field_errors_by_constraint(validation.errors),
                settings=settings,
            )

        current_settings = self._with_all_constraints(
            self._cache.get_constraint_settings()
        )
        settings_changed = settings != current_settings
        had_generated_results = bool(
            self._cache.get_generated_schedules()
            or self._cache.get_ranked_schedules()
        )

        if settings_changed:
            self._cache.set_constraint_settings(settings)
            self.reload_from_cache()
            schedules_invalidated = had_generated_results
            message = (
                "Settings saved. Existing generated schedules were invalidated."
                if schedules_invalidated
                else "Settings saved."
            )
        else:
            schedules_invalidated = False
            message = "Settings unchanged."

        return SchedulingSettingsSaveResult(
            success=True,
            message=message,
            settings_changed=settings_changed,
            schedules_invalidated=schedules_invalidated,
            settings=self._clone_settings(settings),
        )

    def reload_from_cache(self) -> list[SchedulingSettingRow]:
        """Discard draft edits and restore the settings currently in cache."""
        settings = self._with_all_constraints(
            self._cache.get_constraint_settings()
        )
        self._enabled = {}
        self._k_text = {}

        for constraint_type in ThresholdConstraintType:
            setting = settings.constraints[constraint_type]
            self._enabled[constraint_type] = bool(setting.enabled)
            self._k_text[constraint_type] = self._k_text_from_setting(setting)

        return self.rows()

    def has_unsaved_changes(self) -> bool:
        """Return True when the current draft differs from cached settings."""
        return (
            self._settings_from_draft()
            != self._with_all_constraints(self._cache.get_constraint_settings())
        )

    def draft_settings(self) -> SchedulingConstraintSettings:
        """Return a detached settings object built from current inputs."""
        return self._settings_from_draft()

    def _row_for(
        self,
        constraint_type: ThresholdConstraintType,
    ) -> SchedulingSettingRow:
        requirement_id, title, description = _REQUIREMENT_COPY[constraint_type]
        enabled = self._enabled[constraint_type]
        return SchedulingSettingRow(
            constraint_type=constraint_type,
            key=constraint_type.value,
            requirement_id=requirement_id,
            title=title,
            description=description,
            enabled=enabled,
            k_text=self._k_text[constraint_type],
            k_input_enabled=enabled,
        )

    def _settings_from_draft(self) -> SchedulingConstraintSettings:
        constraints: dict[ThresholdConstraintType, ThresholdConstraintSetting] = {}

        for constraint_type in ThresholdConstraintType:
            enabled = self._enabled[constraint_type]
            raw_value = self._k_text[constraint_type]
            k_value = self._coerce_k_value(raw_value, enabled)
            constraints[constraint_type] = ThresholdConstraintSetting(
                enabled=enabled,
                k=k_value,  # type: ignore[arg-type]
            )

        return SchedulingConstraintSettings(constraints=constraints)

    @staticmethod
    def _coerce_k_value(
        raw_value: str,
        enabled: bool,
    ) -> int | str:
        if not enabled:
            try:
                return int(raw_value)
            except ValueError:
                return 0

        try:
            return int(raw_value)
        except ValueError:
            return raw_value

    @staticmethod
    def _clone_settings(
        settings: SchedulingConstraintSettings,
    ) -> SchedulingConstraintSettings:
        return SchedulingConstraintSettings(
            constraints={
                constraint_type: ThresholdConstraintSetting(
                    enabled=setting.enabled,
                    k=setting.k,
                )
                for constraint_type, setting in settings.constraints.items()
                if setting is not None
            }
        )

    @classmethod
    def _with_all_constraints(
        cls,
        settings: SchedulingConstraintSettings,
    ) -> SchedulingConstraintSettings:
        complete = SchedulingConstraintSettings.default_configuration()

        if settings.constraints is None:
            return complete

        for constraint_type in ThresholdConstraintType:
            setting = settings.constraints.get(constraint_type)
            if setting is not None:
                complete.constraints[constraint_type] = ThresholdConstraintSetting(
                    enabled=setting.enabled,
                    k=setting.k,
                )

        return complete

    @staticmethod
    def _k_text_from_setting(setting: ThresholdConstraintSetting) -> str:
        if setting.enabled or setting.k not in (0, None):
            return str(setting.k)
        return ""

    @staticmethod
    def _field_errors_by_constraint(errors) -> dict[str, list[str]]:
        field_errors: dict[str, list[str]] = {}

        for error in errors:
            matched_key = None
            for constraint_type in ThresholdConstraintType:
                if constraint_type.value in error.field_path:
                    matched_key = constraint_type.value
                    break

            key = matched_key or error.field_path
            field_errors.setdefault(key, []).append(error.message)

        return field_errors

    @staticmethod
    def _require_known_constraint(
        constraint_type: ThresholdConstraintType,
    ) -> None:
        if not isinstance(constraint_type, ThresholdConstraintType):
            raise ValueError(f"Unknown threshold constraint: {constraint_type!r}")
