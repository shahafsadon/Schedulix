"""
test_settings_validator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for ``SchedulingSettingsValidator`` (SCRUM-143).

Each test class targets one specific validation responsibility so failures
are easy to localise.  Tests are intentionally written without any GUI
imports to verify that the validator is fully decoupled from the View layer.
"""

from __future__ import annotations

import pytest

from application.settings_validator import (
    SchedulingSettingsValidator,
    ValidationError,
    ValidationResult,
    ValidationSeverity,
)
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from ranking_settings import (
    RankingCriterion,
    RankingPreference,
    RankingSettings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_disabled() -> SchedulingConstraintSettings:
    """Return a default config with every constraint disabled (k=0)."""
    return SchedulingConstraintSettings.default_configuration()


def _enabled(k: int) -> ThresholdConstraintSetting:
    return ThresholdConstraintSetting(enabled=True, k=k)


def _disabled(k: int = 0) -> ThresholdConstraintSetting:
    return ThresholdConstraintSetting(enabled=False, k=k)


def _full_settings(**overrides: ThresholdConstraintSetting) -> SchedulingConstraintSettings:
    """Build a SchedulingConstraintSettings with all entries present.

    Each constraint defaults to disabled(k=0).  Pass keyword arguments
    whose names match ``ThresholdConstraintType`` member names to override
    individual entries.
    """
    base = {ct: _disabled() for ct in ThresholdConstraintType}
    for name, setting in overrides.items():
        ct = ThresholdConstraintType[name]
        base[ct] = setting
    return SchedulingConstraintSettings(constraints=base)


def _ranking(*criteria: RankingCriterion) -> RankingSettings:
    """Build a RankingSettings from a list of criteria (all descending)."""
    return RankingSettings(
        priority_list=[RankingPreference(criterion=c) for c in criteria]
    )


# ---------------------------------------------------------------------------
# ValidationResult unit tests
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_ok_factory_is_valid(self) -> None:
        result = ValidationResult.ok()
        assert result.is_valid is True
        assert result.has_errors is False
        assert result.errors == ()

    def test_from_errors_marks_invalid(self) -> None:
        error = ValidationError(
            field_path="foo.bar",
            message="something went wrong",
        )
        result = ValidationResult.from_errors([error])
        assert result.is_valid is False
        assert result.has_errors is True
        assert len(result.errors) == 1

    def test_error_messages_returns_strings(self) -> None:
        error = ValidationError(
            field_path="a.b",
            message="bad value",
        )
        result = ValidationResult.from_errors([error])
        messages = result.error_messages
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert "bad value" in messages[0]
        assert "a.b" in messages[0]

    def test_str_representation_includes_severity(self) -> None:
        error = ValidationError(
            field_path="x.y",
            message="oops",
            severity=ValidationSeverity.ERROR,
        )
        text = str(error)
        assert "ERROR" in text
        assert "x.y" in text
        assert "oops" in text


# ---------------------------------------------------------------------------
# Constraint settings validation
# ---------------------------------------------------------------------------

class TestConstraintSettingsValidation:
    """Tests for _check_constraint_settings."""

    def setup_method(self) -> None:
        self.validator = SchedulingSettingsValidator()

    # --- Happy-path ---

    def test_all_disabled_is_valid(self) -> None:
        result = self.validator.validate_constraint_settings(_all_disabled())
        assert result.is_valid

    def test_single_enabled_valid_k_is_valid(self) -> None:
        settings = _full_settings(mandatory_gap_days=_enabled(3))
        result = self.validator.validate_constraint_settings(settings)
        assert result.is_valid

    def test_all_enabled_with_valid_k_is_valid(self) -> None:
        settings = _full_settings(
            mandatory_gap_days=_enabled(3),
            any_course_gap_days=_enabled(2),
            elective_conflicts_per_program=_enabled(1),
            mandatory_span_days=_enabled(10),
            max_exams_per_day=_enabled(5),
        )
        result = self.validator.validate_constraint_settings(settings)
        assert result.is_valid

    def test_disabled_constraint_with_k_zero_is_valid(self) -> None:
        # k=0 is only invalid for *enabled* constraints.
        settings = _full_settings(mandatory_gap_days=_disabled(0))
        result = self.validator.validate_constraint_settings(settings)
        assert result.is_valid

    # --- k range errors ---

    def test_enabled_k_zero_is_invalid(self) -> None:
        settings = _full_settings(mandatory_gap_days=_enabled(0))
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        paths = [e.field_path for e in result.errors]
        assert any("mandatory_gap_days" in p and ".k" in p for p in paths)

    def test_enabled_k_negative_is_invalid(self) -> None:
        settings = _full_settings(any_course_gap_days=_enabled(-5))
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid

    def test_multiple_invalid_k_values_all_reported(self) -> None:
        settings = _full_settings(
            mandatory_gap_days=_enabled(0),
            any_course_gap_days=_enabled(-1),
        )
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        assert len(result.errors) == 2

    # --- k type errors ---

    def test_enabled_k_string_is_invalid(self) -> None:
        setting = ThresholdConstraintSetting(enabled=True, k="three")  # type: ignore[arg-type]
        settings = _full_settings(mandatory_gap_days=setting)
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        assert any("integer" in e.message for e in result.errors)

    def test_enabled_k_float_is_invalid(self) -> None:
        setting = ThresholdConstraintSetting(enabled=True, k=2.5)  # type: ignore[arg-type]
        settings = _full_settings(mandatory_gap_days=setting)
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid

    def test_enabled_k_bool_is_invalid(self) -> None:
        # bool is a subclass of int; the validator must reject it explicitly.
        setting = ThresholdConstraintSetting(enabled=True, k=True)  # type: ignore[arg-type]
        settings = _full_settings(mandatory_gap_days=setting)
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid

    # --- Missing entry errors ---

    def test_missing_constraint_type_entry_is_invalid(self) -> None:
        partial: dict = {
            ThresholdConstraintType.mandatory_gap_days: _disabled(),
        }
        settings = SchedulingConstraintSettings(constraints=partial)
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        # Four entries are missing; each should produce one error.
        missing_errors = [
            e for e in result.errors
            if "Missing entry" in e.message
        ]
        assert len(missing_errors) == 4

    def test_none_constraints_dict_is_invalid(self) -> None:
        settings = SchedulingConstraintSettings(constraints=None)  # type: ignore[arg-type]
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        assert any("constraints mapping is None" in e.message for e in result.errors)

    def test_none_individual_setting_is_invalid(self) -> None:
        base = {ct: _disabled() for ct in ThresholdConstraintType}
        base[ThresholdConstraintType.max_exams_per_day] = None  # type: ignore[assignment]
        settings = SchedulingConstraintSettings(constraints=base)
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        assert any("max_exams_per_day" in e.field_path for e in result.errors)

    # --- field_path precision ---

    def test_error_field_path_identifies_constraint_and_k(self) -> None:
        settings = _full_settings(elective_conflicts_per_program=_enabled(-1))
        result = self.validator.validate_constraint_settings(settings)
        assert not result.is_valid
        error = result.errors[0]
        assert "elective_conflicts_per_program" in error.field_path
        assert ".k" in error.field_path


# ---------------------------------------------------------------------------
# Ranking settings validation
# ---------------------------------------------------------------------------

class TestRankingSettingsValidation:
    """Tests for _check_ranking_settings."""

    def setup_method(self) -> None:
        self.validator = SchedulingSettingsValidator()

    # --- Happy-path ---

    def test_empty_priority_list_is_valid(self) -> None:
        result = self.validator.validate_ranking_settings(
            RankingSettings(priority_list=[])
        )
        assert result.is_valid

    def test_single_criterion_is_valid(self) -> None:
        result = self.validator.validate_ranking_settings(
            _ranking(RankingCriterion.min_mandatory_gap)
        )
        assert result.is_valid

    def test_all_five_criteria_no_duplicates_is_valid(self) -> None:
        result = self.validator.validate_ranking_settings(
            _ranking(
                RankingCriterion.min_mandatory_gap,
                RankingCriterion.average_all_gap,
                RankingCriterion.elective_collision_count,
                RankingCriterion.mandatory_span,
                RankingCriterion.max_exams_per_day,
            )
        )
        assert result.is_valid

    # --- Duplicate criterion errors ---

    def test_duplicate_criterion_is_invalid(self) -> None:
        settings = RankingSettings.__new__(RankingSettings)
        # Bypass __post_init__ to simulate a mutated-after-construction list.
        object.__setattr__(
            settings,
            "priority_list",
            [
                RankingPreference(criterion=RankingCriterion.min_mandatory_gap),
                RankingPreference(criterion=RankingCriterion.average_all_gap),
                RankingPreference(criterion=RankingCriterion.min_mandatory_gap),
            ],
        )
        result = self.validator.validate_ranking_settings(settings)
        assert not result.is_valid
        assert any("Duplicate" in e.message for e in result.errors)
        assert any("min_mandatory_gap" in e.message for e in result.errors)

    def test_duplicate_criterion_field_path_includes_index(self) -> None:
        settings = RankingSettings.__new__(RankingSettings)
        object.__setattr__(
            settings,
            "priority_list",
            [
                RankingPreference(criterion=RankingCriterion.mandatory_span),
                RankingPreference(criterion=RankingCriterion.mandatory_span),
            ],
        )
        result = self.validator.validate_ranking_settings(settings)
        assert not result.is_valid
        # The duplicate appears at index 1.
        assert any("[1]" in e.field_path for e in result.errors)

    # --- None / invalid-type guards ---

    def test_none_priority_list_is_invalid(self) -> None:
        settings = RankingSettings.__new__(RankingSettings)
        object.__setattr__(settings, "priority_list", None)
        result = self.validator.validate_ranking_settings(settings)
        assert not result.is_valid
        assert any("priority_list is None" in e.message for e in result.errors)

    def test_none_entry_in_priority_list_is_invalid(self) -> None:
        settings = RankingSettings.__new__(RankingSettings)
        object.__setattr__(
            settings,
            "priority_list",
            [
                RankingPreference(criterion=RankingCriterion.min_mandatory_gap),
                None,  # type: ignore[list-item]
            ],
        )
        result = self.validator.validate_ranking_settings(settings)
        assert not result.is_valid
        assert any("position 1 is None" in e.message for e in result.errors)

    def test_invalid_criterion_type_is_invalid(self) -> None:
        fake_preference = RankingPreference.__new__(RankingPreference)
        object.__setattr__(fake_preference, "criterion", "not_a_criterion")
        object.__setattr__(fake_preference, "descending", True)

        settings = RankingSettings.__new__(RankingSettings)
        object.__setattr__(settings, "priority_list", [fake_preference])

        result = self.validator.validate_ranking_settings(settings)
        assert not result.is_valid
        assert any("not a valid RankingCriterion" in e.message for e in result.errors)


# ---------------------------------------------------------------------------
# Combined validate() method
# ---------------------------------------------------------------------------

class TestCombinedValidation:
    """Tests for the combined validate() entry-point."""

    def setup_method(self) -> None:
        self.validator = SchedulingSettingsValidator()

    def test_both_none_is_valid(self) -> None:
        result = self.validator.validate(
            constraint_settings=None,
            ranking_settings=None,
        )
        assert result.is_valid

    def test_valid_constraint_and_ranking_is_valid(self) -> None:
        result = self.validator.validate(
            constraint_settings=_full_settings(mandatory_gap_days=_enabled(2)),
            ranking_settings=_ranking(RankingCriterion.average_all_gap),
        )
        assert result.is_valid

    def test_errors_from_both_phases_are_combined(self) -> None:
        # Constraint error: enabled with k=0.
        bad_constraints = _full_settings(mandatory_gap_days=_enabled(0))

        # Ranking error: duplicate criterion (bypass __post_init__).
        bad_ranking = RankingSettings.__new__(RankingSettings)
        object.__setattr__(
            bad_ranking,
            "priority_list",
            [
                RankingPreference(criterion=RankingCriterion.min_mandatory_gap),
                RankingPreference(criterion=RankingCriterion.min_mandatory_gap),
            ],
        )

        result = self.validator.validate(
            constraint_settings=bad_constraints,
            ranking_settings=bad_ranking,
        )
        assert not result.is_valid
        assert len(result.errors) >= 2

    def test_only_constraint_validated_when_ranking_is_none(self) -> None:
        bad_constraints = _full_settings(mandatory_gap_days=_enabled(-1))
        result = self.validator.validate(
            constraint_settings=bad_constraints,
            ranking_settings=None,
        )
        assert not result.is_valid
        # All errors must reference the constraint path.
        assert all(
            "constraint_settings" in e.field_path for e in result.errors
        )

    def test_only_ranking_validated_when_constraint_is_none(self) -> None:
        bad_ranking = RankingSettings.__new__(RankingSettings)
        object.__setattr__(
            bad_ranking,
            "priority_list",
            [
                RankingPreference(criterion=RankingCriterion.max_exams_per_day),
                RankingPreference(criterion=RankingCriterion.max_exams_per_day),
            ],
        )
        result = self.validator.validate(
            constraint_settings=None,
            ranking_settings=bad_ranking,
        )
        assert not result.is_valid
        assert all(
            "ranking_settings" in e.field_path for e in result.errors
        )

    def test_convenience_validate_constraint_settings(self) -> None:
        result = self.validator.validate_constraint_settings(_all_disabled())
        assert result.is_valid

    def test_convenience_validate_ranking_settings(self) -> None:
        result = self.validator.validate_ranking_settings(
            RankingSettings(priority_list=[])
        )
        assert result.is_valid

    # --- Severity ---

    def test_all_emitted_errors_have_error_severity(self) -> None:
        bad_constraints = _full_settings(
            mandatory_gap_days=_enabled(0),
            any_course_gap_days=_enabled(-1),
        )
        result = self.validator.validate_constraint_settings(bad_constraints)
        assert all(
            e.severity == ValidationSeverity.ERROR for e in result.errors
        )
